# app/logging_conf.py

from __future__ import annotations

import logging
import os
from logging.config import dictConfig

from dotenv import load_dotenv


def setup_logging() -> None:
    """
    Настройка логирования + загрузка .env.

    Важно:
    - load_dotenv() вызывается здесь, чтобы переменные окружения
      были доступны уже на этапе инициализации LLMClient и прочих компонентов.
    """

    # Загружаем переменные из .env (если есть)
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Можно при желании залогировать факт инициализации
    logging.getLogger(__name__).info("Логирование настроено, LOG_LEVEL=%s", log_level)
