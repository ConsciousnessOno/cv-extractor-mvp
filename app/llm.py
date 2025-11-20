# app/llm.py

"""
Обвязка LLM для извлечения структурированных данных из резюме.

Задачи:
- собрать промпт (system + user) с описанием схемы
- позвать модель в JSON-режиме
- распарсить JSON, провалидировать через Pydantic (CVOut)
- при ошибке валидации/JSON сделать re-ask с текстом ошибки
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI
from pydantic import ValidationError

from .models import CVOut

logger = logging.getLogger(__name__)


def _build_schema_hint() -> str:
    """
    Краткое текстовое описание схемы, которое мы отдадим в промпт.
    Этого достаточно, чтобы модель не плодила лишние поля.
    """
    return """
Ожидаемый JSON-формат:

{
  "name": string | null,
  "contacts": {
    "email": string | null,
    "phone_e164": string | null,
    "location": string | null
  },
  "links": {
    "linkedin": string | null,
    "github": string | null,
    "portfolio": string | null
  },
  "skills": [string, ...],
  "education": [
    {
      "degree": string | null,
      "institution": string | null,
      "year": int | null
    },
    ...
  ],
  "jobs": [
    {
      "company": string | null,
      "title": string | null,
      "start": "YYYY-MM" | null,
      "end": "YYYY-MM" | null,
      "desc": string | null
    },
    ...
  ],
  "languages": [
    {
      "name": string,
      "level": string | null
    },
    ...
  ]
}

Требования:
- возвращай только один JSON-объект без текста до/после.
- если значение неизвестно, используй null или пустой список.
- не добавляй других полей.
    """.strip()


def _build_messages(text: str, lang: Optional[str], validation_errors: Optional[str]) -> list[dict]:
    """
    Формируем сообщения для LLM.
    """
    lang_label = lang or "auto"

    system_msg = (
        "Ты помощник, который извлекает структурированные поля из текста резюме. "
        "Всегда отвечай строго одним валидным JSON-объектом. "
        "Если какое-то поле неизвестно, ставь null или пустой список. "
        "Не добавляй никакого текста до или после JSON. "
        "Строго следуй предоставленной схеме."
    )

    user_parts = [
        f"Язык резюме: {lang_label}.",
        "Вот текст резюме:",
        text,
        "",
        "Верни JSON строго в следующем формате (только объект, без комментариев):",
        _build_schema_hint(),
    ]

    if validation_errors:
        user_parts.append("")
        user_parts.append(
            "Предыдущий ответ не прошёл валидацию. Вот ошибки валидации Pydantic:"
        )
        user_parts.append(validation_errors)
        user_parts.append(
            "Исправь ответ, чтобы он строго соответствовал схеме. Не изменяй семантику данных, только формат."
        )

    user_msg = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


class LLMClient:
    """
    Обёртка над OpenAI-клиентом.

    - использует JSON-режим (response_format = json_object)
    - делает до REASK_MAX повторных попыток, если JSON/валидация сломались
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[int] = None,
        reask_max: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout_sec = timeout_sec or int(os.getenv("TIMEOUT_SEC", "30"))
        self.reask_max = (
            reask_max if reask_max is not None else int(os.getenv("REASK_MAX", "1"))
        )

        if not self.api_key:
            logger.warning(
                "LLM_API_KEY не установлен. Вызовы LLM будут падать, "
                "пока не будет задан ключ в переменных окружения."
            )
            self.client: Optional[OpenAI] = None
        else:
            self.client = OpenAI(api_key=self.api_key)

        logger.info(
            "LLMClient инициализирован",
            extra={
                "model": self.model,
                "timeout_sec": self.timeout_sec,
                "reask_max": self.reask_max,
            },
        )

    def _call_llm_once(
        self,
        text: str,
        lang: Optional[str],
        validation_errors: Optional[str],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Один вызов модели.

        Возвращает:
        - raw_json_dict: dict (уже распарсенный JSON)
        - meta: dict с model, tokens_in, tokens_out
        """
        if self.client is None:
            raise RuntimeError(
                "LLM клиент не сконфигурирован (нет LLM_API_KEY). "
                "Установи LLM_API_KEY в .env."
            )

        messages = _build_messages(text=text, lang=lang, validation_errors=validation_errors)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            timeout=self.timeout_sec,
        )

        choice = response.choices[0]
        content = choice.message.content

        if content is None:
            raise RuntimeError("LLM вернул пустой контент")

        try:
            raw_json = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM вернул невалидный JSON: {exc}") from exc

        usage = response.usage
        meta = {
            "model": response.model,
            "tokens_in": usage.prompt_tokens if usage else None,
            "tokens_out": usage.completion_tokens if usage else None,
        }

        return raw_json, meta

    def extract_cv(self, text: str, lang: Optional[str] = None) -> Tuple[CVOut, Dict[str, Any]]:
        """
        Главный публичный метод.

        Делает до (1 + REASK_MAX) попыток:
        - вызывает LLM
        - пытается провалидировать ответ через CVOut
        - если валидация падает, повторяет запрос, передавая текст ошибки в промпт
        """
        validation_errors: Optional[str] = None
        last_exc: Optional[Exception] = None
        last_meta: Dict[str, Any] = {}

        attempts = 1 + max(self.reask_max, 0)

        for attempt in range(attempts):
            try:
                raw_json, meta = self._call_llm_once(
                    text=text,
                    lang=lang,
                    validation_errors=validation_errors,
                )
                last_meta = meta

                cv = CVOut.model_validate(raw_json)
                # Если мы сюда дошли — JSON корректен и прошёл Pydantic
                return cv, last_meta

            except ValidationError as exc:
                # Ошибка структуры — даём модели шанс исправиться
                validation_errors = exc.json()
                last_exc = exc
                logger.warning(
                    "LLM ответ не прошёл валидацию, попытка %s/%s",
                    attempt + 1,
                    attempts,
                )
            except Exception as exc:
                # прочие ошибки (сетевые, JSON и т.д.)
                validation_errors = str(exc)
                last_exc = exc
                logger.warning(
                    "Ошибка при вызове LLM, попытка %s/%s: %s",
                    attempt + 1,
                    attempts,
                    exc,
                )

        # Если все попытки исчерпаны — пробрасываем последнюю ошибку
        if last_exc:
            raise last_exc

        raise RuntimeError("Не удалось получить валидный ответ от LLM без объяснения причин.")
