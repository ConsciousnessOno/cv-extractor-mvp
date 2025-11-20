# tests/test_validate.py

from app.models import CVOut, Contacts, LinkSet, EducationItem, JobItem, LanguageItem


def test_cvout_default_valid():
    cv = CVOut()
    assert cv.contacts is not None
    assert cv.links is not None
    assert isinstance(cv.skills, list)
    assert isinstance(cv.education, list)
    assert isinstance(cv.jobs, list)
    assert isinstance(cv.languages, list)


def test_language_item_required_name():
    lang = LanguageItem(name="English", level="C1")
    assert lang.name == "English"
    assert lang.level == "C1"


def test_job_item_date_pattern():
    job = JobItem(
        company="Test Corp",
        title="Engineer",
        start="2023-01",
        end="2023-06",
    )
    assert job.start == "2023-01"
    assert job.end == "2023-06"
