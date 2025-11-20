# app/main.py

from __future__ import annotations

import logging
import time
import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException

from .logging_conf import setup_logging
from .models import ParseResumeRequest, ParseResumeResponse, CVOut, CVMeta
from .normalize import normalize_cv
from .llm import LLMClient
from .store import (
    init_db,
    compute_text_hash,
    get_cached_result,
    save_result,
    log_run,
)

# Настраиваем логирование и загружаем .env
setup_logging()
logger = logging.getLogger(__name__)

# Инициализируем SQLite
init_db()

# Инициализируем LLM-клиент один раз на процесс
llm_client = LLMClient()

app = FastAPI(
    title="CV Extractor MVP",
    version="0.1.0",
    description="Мини-сервис для извлечения структурированных данных из резюме.",
)


@app.get("/")
async def root():
    """
    Базовый endpoint для проверки руками в браузере.
    """
    return {
        "app": "CV Extractor MVP",
        "status": "ok",
        "docs": "/docs",
        "endpoints": ["/health", "/parse_resume"],
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Простой health-check для мониторинга.
    """
    return {"status": "ok"}


@app.post("/parse_resume", response_model=ParseResumeResponse)
async def parse_resume(payload: ParseResumeRequest) -> ParseResumeResponse:
    """
    Основная точка входа: принимает сырой текст резюме и язык,
    возвращает нормализованный JSON по схеме.

    Логика:
    1) проверка входа
    2) вычисление text_hash
    3) попытка отдать результат из кэша (SQLite.results)
    4) если кэша нет:
       - вызвать LLM
       - провалидировать и нормализовать
       - сохранить результат в SQLite.results
    5) в любом успешном случае залогировать run в SQLite.runs
    """
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Field 'text' must be non-empty")

    start_ts = time.perf_counter()
    request_id = str(uuid.uuid4())
    text_hash = compute_text_hash(payload.text)

    try:
        # 1. Проверяем кэш по хэшу текста
        cached_cv = get_cached_result(text_hash)
        if cached_cv is not None:
            latency_ms = int((time.perf_counter() - start_ts) * 1000)

            meta = CVMeta(
                request_id=request_id,
                model=None,
                tokens_in=None,
                tokens_out=None,
                latency_ms=latency_ms,
                status="ok_cached",
            )

            log_run(
                request_id=request_id,
                text_hash=text_hash,
                status="cache_hit",
                model=None,
                tokens_in=None,
                tokens_out=None,
                latency_ms=latency_ms,
            )

            logger.info(
                "parse_resume_cache_hit",
                extra={
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                },
            )

            return ParseResumeResponse(data=cached_cv, meta=meta)

        # 2. Кэша нет — вызываем LLM и нормализуем
        cv_raw, llm_meta = llm_client.extract_cv(
            text=payload.text,
            lang=payload.lang,
        )

        cv_normalized: CVOut = normalize_cv(cv_raw, raw_text=payload.text)

        latency_ms = int((time.perf_counter() - start_ts) * 1000)

        meta = CVMeta(
            request_id=request_id,
            model=llm_meta.get("model"),
            tokens_in=llm_meta.get("tokens_in"),
            tokens_out=llm_meta.get("tokens_out"),
            latency_ms=latency_ms,
            status="ok",
        )

        # 3. Сохраняем результат в кэш
        save_result(text_hash, cv_normalized)

        # 4. Логируем успешный run
        log_run(
            request_id=request_id,
            text_hash=text_hash,
            status="ok",
            model=meta.model,
            tokens_in=meta.tokens_in,
            tokens_out=meta.tokens_out,
            latency_ms=latency_ms,
        )

        logger.info(
            "parse_resume_success",
            extra={
                "request_id": request_id,
                "latency_ms": latency_ms,
                "model": meta.model,
                "tokens_in": meta.tokens_in,
                "tokens_out": meta.tokens_out,
            },
        )

        return ParseResumeResponse(data=cv_normalized, meta=meta)

    except HTTPException:
        # FastAPI сам обработает
        raise
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start_ts) * 1000)

        logger.exception(
            "parse_resume_failed",
            extra={
                "request_id": request_id,
                "latency_ms": latency_ms,
            },
        )

        # Пишем неуспешный run в БД
        log_run(
            request_id=request_id,
            text_hash=text_hash,
            status="error",
            model=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=latency_ms,
        )

        raise HTTPException(
            status_code=500,
            detail={
                "request_id": request_id,
                "error": "internal_error",
                "message": str(exc),
            },
        )
