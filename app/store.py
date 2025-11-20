# app/store.py

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from .models import CVOut

logger = logging.getLogger(__name__)

DB_URL_DEFAULT = "sqlite:///./cv_extractor.db"


def _get_db_path() -> str:
    """
    Преобразуем DB_URL в путь до sqlite-файла.

    Поддерживаем:
    - sqlite:///./cv_extractor.db
    - sqlite:///cv_extractor.db
    - cv_extractor.db
    """
    url = os.getenv("DB_URL", DB_URL_DEFAULT)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "", 1)
    return url


DB_PATH = _get_db_path()


def init_db() -> None:
    """
    Инициализация SQLite: создаём таблицы, если их нет.

    Таблицы:
    - results(text_hash PRIMARY KEY, cv_json)
    - runs(id PK, request_id, text_hash, status, model, tokens_in, tokens_out, latency_ms, created_at)
    """
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                text_hash TEXT PRIMARY KEY,
                cv_json   TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id  TEXT NOT NULL,
                text_hash   TEXT NOT NULL,
                status      TEXT NOT NULL,
                model       TEXT,
                tokens_in   INTEGER,
                tokens_out  INTEGER,
                latency_ms  INTEGER,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()
        logger.info("SQLite инициализирован: %s", DB_PATH)
    finally:
        conn.close()


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def compute_text_hash(text: str) -> str:
    """
    Детерминированный hash текста резюме для идемпотентности.

    Используем SHA-256 от trimmed UTF-8.
    """
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def get_cached_result(text_hash: str) -> Optional[CVOut]:
    """
    Возвращает CVOut из таблицы results по text_hash или None.
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT cv_json FROM results WHERE text_hash = ?", (text_hash,))
        row = cur.fetchone()

    if not row:
        return None

    cv_json = row[0]
    try:
        return CVOut.model_validate_json(cv_json)
    except Exception as exc:
        logger.warning(
            "Не удалось провалидировать кэшированный результат text_hash=%s: %s",
            text_hash,
            exc,
        )
        return None


def save_result(text_hash: str, cv: CVOut) -> None:
    """
    Сохраняет (или обновляет) результат парсинга по хэшу текста.
    """
    cv_json = cv.model_dump_json()
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO results (text_hash, cv_json)
            VALUES (?, ?)
            """,
            (text_hash, cv_json),
        )


def log_run(
    request_id: str,
    text_hash: str,
    status: str,
    model: Optional[str],
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    latency_ms: int,
) -> None:
    """
    Логируем один запуск в таблицу runs.
    """
    created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO runs (
                request_id, text_hash, status, model,
                tokens_in, tokens_out, latency_ms, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                text_hash,
                status,
                model,
                tokens_in,
                tokens_out,
                latency_ms,
                created_at,
            ),
        )
