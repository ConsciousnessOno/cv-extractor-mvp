# tests/test_normalize.py

from app.models import CVOut
from app.normalize import (
    normalize_cv,
    normalize_phone_e164,
    normalize_date_to_yyyy_mm,
    normalize_skills,
)


def test_normalize_cv_fallback_email_and_phone():
    text = "Иван Иванов\nEmail: ivan@example.com\nТел: +7 (999) 123-45-67"
    cv = CVOut()
    result = normalize_cv(cv, raw_text=text)

    assert result.contacts.email == "ivan@example.com"
    assert result.contacts.phone_e164 == "+79991234567"


def test_normalize_phone_russian():
    assert normalize_phone_e164("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone_e164("8 999 123 45 67") == "+79991234567"


def test_normalize_date_formats():
    assert normalize_date_to_yyyy_mm("2023-06") == "2023-06"
    assert normalize_date_to_yyyy_mm("06/2023") == "2023-06"
    assert normalize_date_to_yyyy_mm("Июнь 2023") == "2023-06"
    assert normalize_date_to_yyyy_mm("2023") == "2023-01"


def test_normalize_skills_lower_and_dedup():
    skills = ["Python", " python ", "FastAPI", "", "PYTHON"]
    norm = normalize_skills(skills)
    assert norm == ["python", "fastapi"]


def test_normalize_cv_skills_pipeline():
    cv = CVOut(skills=["Python", "FastAPI", "python"])
    result = normalize_cv(cv, raw_text="dummy")
    assert result.skills == ["python", "fastapi"]
