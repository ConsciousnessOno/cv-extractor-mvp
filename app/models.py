# app/models.py

from __future__ import annotations

from typing import List, Optional, Literal, Annotated

from pydantic import BaseModel, EmailStr, HttpUrl, Field


# Общий тип для дат формата YYYY-MM
DateYYYYMM = Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]


class Contacts(BaseModel):
    email: Optional[EmailStr] = None
    phone_e164: Optional[str] = Field(
        default=None,
        description="Номер телефона в формате E.164, например +79261234567",
    )
    location: Optional[str] = None


class LinkSet(BaseModel):
    linkedin: Optional[HttpUrl] = None
    github: Optional[HttpUrl] = None
    portfolio: Optional[HttpUrl] = None


class EducationItem(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = Field(
        default=None,
        description="Год окончания (четыре цифры)",
        ge=1900,
        le=2100,
    )


class JobItem(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[DateYYYYMM] = Field(
        default=None,
        description="Дата начала в формате YYYY-MM",
    )
    end: Optional[DateYYYYMM] = Field(
        default=None,
        description="Дата окончания в формате YYYY-MM",
    )
    desc: Optional[str] = None


class LanguageItem(BaseModel):
    name: str = Field(..., min_length=1)
    level: Optional[str] = Field(
        default=None,
        description="Уровень владения языком (A1–C2, B1, носитель и т.п.)",
    )


class CVOut(BaseModel):
    name: Optional[str] = None
    contacts: Contacts = Contacts()
    links: LinkSet = LinkSet()
    skills: List[str] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    jobs: List[JobItem] = Field(default_factory=list)
    languages: List[LanguageItem] = Field(default_factory=list)


class CVMeta(BaseModel):
    request_id: str
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: int
    # добавили ok_cached, чтобы кэш не падал
    status: Literal["ok", "ok_cached", "error"]


class ParseResumeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    lang: Optional[str] = Field(
        default=None,
        description="Язык резюме (ru/en/auto и т.п.)",
    )


class ParseResumeResponse(BaseModel):
    data: CVOut
    meta: CVMeta
