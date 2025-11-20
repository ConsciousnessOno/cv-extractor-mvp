# app/normalize.py

"""
Нормализация полей: телефон, даты, skills и т.п.

Спринт 2:

- телефон → E.164 (насколько возможно эвристически)
- даты → YYYY-MM
- skills → lower + trim + dedup
- fallback-ы для email/phone по исходному тексту, если LLM/мок их не вытащили
"""

from __future__ import annotations

import re
from typing import Optional

from .models import CVOut

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s\(\)]{7,}\d")

MONTHS = {
    # EN
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
    # RU
    "январь": "01",
    "февраль": "02",
    "март": "03",
    "апрель": "04",
    "май": "05",
    "июнь": "06",
    "июль": "07",
    "август": "08",
    "сентябрь": "09",
    "октябрь": "10",
    "ноябрь": "11",
    "декабрь": "12",
    "янв": "01",
    "фев": "02",
    "мар": "03",
    "апр": "04",
    "июн": "06",
    "июл": "07",
    "авг": "08",
    "сен": "09",
    "сент": "09",
    "окт": "10",
    "ноя": "11",
    "дек": "12",
}


def normalize_cv(cv: CVOut, raw_text: str) -> CVOut:
    """
    Централизованный вход в нормализацию.

    - нормализуем телефон
    - нормализуем даты в jobs
    - skills: lower + trim + dedup
    - fallback-поиск email/phone в исходном тексте, если они пустые
    """
    cv_norm = cv.model_copy(deep=True)

    # Fallback email
    if cv_norm.contacts.email is None:
        m = EMAIL_RE.search(raw_text)
        if m:
            cv_norm.contacts.email = m.group(0).strip()

    # Fallback phone
    if cv_norm.contacts.phone_e164 is None:
        m = PHONE_RE.search(raw_text)
        if m:
            cv_norm.contacts.phone_e164 = m.group(0).strip()

    # Нормализация телефона в E.164 (насколько возможно)
    if cv_norm.contacts.phone_e164:
        cv_norm.contacts.phone_e164 = normalize_phone_e164(cv_norm.contacts.phone_e164)

    # Даты в jobs
    for job in cv_norm.jobs:
        if job.start:
            job.start = normalize_date_to_yyyy_mm(job.start)
        if job.end:
            job.end = normalize_date_to_yyyy_mm(job.end)

    # skills: lower + trim + dedup
    cv_norm.skills = normalize_skills(cv_norm.skills)

    return cv_norm


def normalize_phone_e164(phone_raw: str) -> str:
    """
    Приведение телефона к формату, похожему на E.164.

    Эвристики:
    - убираем пробелы, дефисы, скобки
    - если номер начинается с 8 и длина 11 → считаем РФ, делаем +7XXXXXXXXXX
    - если начинается с 7 и длина 11 → +7XXXXXXXXXX
    - если начинается с + → оставляем + и цифры
    - иначе: берём только цифры и добавляем '+' спереди
    """
    s = phone_raw.strip()

    # Уже нормальный E.164? (+цифры)
    if re.fullmatch(r"\+\d{8,15}", s):
        return s

    # Убираем всё, кроме цифр и '+'
    s = re.sub(r"[^\d+]", "", s)

    # Если начинается с '+', оставляем плюс и цифры
    if s.startswith("+"):
        digits = re.sub(r"\D", "", s[1:])
        if digits:
            return f"+{digits}"
        return phone_raw.strip()

    # Оставляем только цифры
    digits = re.sub(r"\D", "", s)
    if not digits:
        return phone_raw.strip()

    # РФ кейс 8XXXXXXXXXX
    if digits.startswith("8") and len(digits) == 11:
        return f"+7{digits[1:]}"

    # РФ кейс 7XXXXXXXXXX
    if digits.startswith("7") and len(digits) == 11:
        return f"+7{digits[1:]}"

    # Остальное: просто '+' + цифры
    return f"+{digits}"


def normalize_date_to_yyyy_mm(date_raw: str) -> str:
    """
    Привести строку даты к формату YYYY-MM, если возможно.

    Поддерживаем:
    - '2023-06'
    - '06/2023', '6/2023'
    - '2023/6', '2023-6'
    - 'June 2023', 'Июнь 2023', '2023 June', '2023 Июнь'
    - '2023' → '2023-01'

    Если не получилось распарсить — возвращаем исходную строку.
    """
    s = date_raw.strip()
    if not s:
        return s

    # Уже в формате YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s

    # MM/YYYY или M/YYYY
    m = re.match(r"^(\d{1,2})[\/\.\-](\d{4})$", s)
    if m:
        month = int(m.group(1))
        year = int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # YYYY/MM или YYYY-M
    m = re.match(r"^(\d{4})[\/\.\-](\d{1,2})$", s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # 'June 2023' / 'Июнь 2023'
    m = re.match(r"^([A-Za-zА-Яа-яёЁ]+)\s+(\d{4})$", s)
    if m:
        month_name = m.group(1).lower()
        year = int(m.group(2))
        month_num = MONTHS.get(month_name)
        if month_num:
            return f"{year:04d}-{month_num}"

    # '2023 June' / '2023 Июнь'
    m = re.match(r"^(\d{4})\s+([A-Za-zА-Яа-яёЁ]+)$", s)
    if m:
        year = int(m.group(1))
        month_name = m.group(2).lower()
        month_num = MONTHS.get(month_name)
        if month_num:
            return f"{year:04d}-{month_num}"

    # Год без месяца
    if re.fullmatch(r"\d{4}", s):
        year = int(s)
        return f"{year:04d}-01"

    return s


def normalize_skills(skills: list[str]) -> list[str]:
    """
    Приведение списка навыков:
    - strip
    - lower
    - убрать пустые
    - dedup с сохранением порядка
    """
    seen: set[str] = set()
    result: list[str] = []
    for skill in skills:
        if skill is None:
            continue
        s = skill.strip().lower()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        result.append(s)
    return result
