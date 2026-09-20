"""The API contract.

Naming rules (agreed with the frontend):
  * snake_case everywhere;
  * numbers are numbers (age: int, amounts: float), never strings;
  * documents / applications / schemes are referenced by id or slug, never by display text;
  * timestamps are ISO-8601 UTC;
  * the caller's identity is `user_id` (from the token), never an e-mail address.
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import constants as C

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # deliberately permissive: demo accounts use *.local
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def _blank_to_none(v):
    return None if isinstance(v, str) and v.strip() == "" else v


def _one_of(value, allowed, label):
    if value is not None and value not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(allowed)}")
    return value


def _subset(values: list[str], allowed, label) -> list[str]:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ValueError(f"unknown {label}: {', '.join(map(str, bad))}")
    return list(dict.fromkeys(values))  # de-dupe, keep order


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- meta
class DocumentTypeOut(BaseModel):
    type: str
    label: str


class StatusOptionOut(BaseModel):
    value: str
    label: str


class MetaOut(BaseModel):
    genders: list[str]
    categories: list[str]
    states: list[str]
    business_types: list[str]
    business_stages: list[str]
    document_types: list[DocumentTypeOut]
    application_statuses: list[StatusOptionOut]


# --------------------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)
    role: str = "user"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.lower()
        if not EMAIL_RE.match(v):
            raise ValueError("enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:  # bcrypt limit is 72 *bytes*
            raise ValueError("password is too long (max 72 bytes)")
        return v

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _one_of(v, C.SELF_REGISTER_ROLES, "role")


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.lower()


class UserOut(ORM):
    id: str
    full_name: str
    email: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds
    user: UserOut


# --------------------------------------------------------------------------- profile
class ProfileIn(BaseModel):
    """Full replacement of the caller's profile. Blank strings are treated as 'not provided'."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(None, max_length=100)
    age: int | None = Field(None, ge=18, le=120)
    gender: str | None = None
    state: str | None = None
    district: str | None = Field(None, max_length=80)
    category: str | None = None
    occupation: str | None = Field(None, max_length=100)
    business_type: str | None = None
    business_stage: str | None = None
    annual_income: float | None = Field(None, ge=0, le=10_000_000_000)
    annual_turnover: float | None = Field(None, ge=0, le=1_000_000_000)
    funding_required: float | None = Field(None, ge=0, le=100_000_000_000)
    own_contribution: float | None = Field(None, ge=0, le=100_000_000_000)
    funding_purpose: str | None = Field(None, max_length=200)

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, v):
        return _blank_to_none(v)

    @field_validator("gender")
    @classmethod
    def _gender(cls, v):
        return _one_of(v, C.GENDERS, "gender")

    @field_validator("state")
    @classmethod
    def _state(cls, v):
        return _one_of(v, C.STATES, "state")

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        return _one_of(v, C.CATEGORIES, "category")

    @field_validator("business_type")
    @classmethod
    def _btype(cls, v):
        return _one_of(v, C.BUSINESS_TYPES, "business_type")

    @field_validator("business_stage")
    @classmethod
    def _bstage(cls, v):
        return _one_of(v, C.BUSINESS_STAGES, "business_stage")


class ProfileOut(ORM):
    full_name: str | None = None
    age: int | None = None
    gender: str | None = None
    state: str | None = None
    district: str | None = None
    category: str | None = None
    occupation: str | None = None
    business_type: str | None = None
    business_stage: str | None = None
    annual_income: float | None = None
    annual_turnover: float | None = None
    funding_required: float | None = None
    own_contribution: float | None = None
    funding_purpose: str | None = None
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- schemes
class SchemeIn(BaseModel):
    """The fixed Scheme schema. Every field is always present -- no more shape drift between
    the seed data, the admin form and the database."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    full_name: str = Field("", max_length=200)
    scheme_type: str = Field("", max_length=100)
    description: str = Field("", max_length=2000)
    min_amount: float = Field(ge=0, le=100_000_000_000)
    max_amount: float = Field(ge=0, le=100_000_000_000)
    eligible_categories: list[str] = Field(min_length=1)
    business_types: list[str] = Field(min_length=1)
    business_stages: list[str] = Field(min_length=1)
    min_age: int = Field(18, ge=0, le=120)
    max_income: float | None = Field(None, ge=0)
    education: str = Field("", max_length=300)
    purpose: str = Field("", max_length=300)
    interest_rate: str = Field("", max_length=300)
    own_contribution_pct: float = Field(0.10, ge=0, le=1)
    application_channel: str = Field("", max_length=300)
    required_documents: list[str] = []
    benefits: str = Field("", max_length=2000)
    source: str = Field("", max_length=200)
    official_url: str = Field(max_length=500)

    @field_validator("eligible_categories")
    @classmethod
    def _cats(cls, v):
        return _subset(v, C.CATEGORIES, "category")

    @field_validator("business_types")
    @classmethod
    def _types(cls, v):
        return _subset(v, C.BUSINESS_TYPES, "business type")

    @field_validator("business_stages")
    @classmethod
    def _stages(cls, v):
        return _subset(v, C.BUSINESS_STAGES, "business stage")

    @field_validator("required_documents")
    @classmethod
    def _docs(cls, v):
        return _subset(v, tuple(C.DOCUMENT_TYPES), "document type")

    @field_validator("official_url")
    @classmethod
    def _url(cls, v):
        if not URL_RE.match(v):
            raise ValueError("official_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _range(self):
        if self.min_amount > self.max_amount:
            raise ValueError("min_amount cannot exceed max_amount")
        return self


class SchemeOut(ORM):
    id: str
    name: str
    full_name: str
    scheme_type: str
    description: str
    min_amount: float
    max_amount: float
    eligible_categories: list[str]
    business_types: list[str]
    business_stages: list[str]
    min_age: int
    max_income: float | None
    education: str
    purpose: str
    interest_rate: str
    own_contribution_pct: float
    application_channel: str
    required_documents: list[str]
    benefits: str
    source: str
    official_url: str
    updated_at: datetime | None = None


class CheckOut(BaseModel):
    status: Literal["ok", "warn", "bad"]
    text: str
    action: str | None = None


class SchemeMatchOut(BaseModel):
    scheme: SchemeOut
    eligibility_status: Literal["eligible", "potentially_eligible", "not_eligible"]
    match_pct: int
    checks: list[CheckOut]


# --------------------------------------------------------------------------- documents
class DocumentStatusOut(BaseModel):
    type: str
    label: str
    status: Literal["uploaded", "missing"]
    document_id: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    uploaded_at: datetime | None = None


class DocumentListOut(BaseModel):
    documents: list[DocumentStatusOut]
    completion_pct: int


# --------------------------------------------------------------------------- partners
class PartnerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    partner_type: str = Field("Partner", max_length=80)
    state: str | None = Field(None, max_length=50)          # None => pan-India
    district: str | None = Field(None, max_length=80)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    coverage: str = Field("", max_length=200)
    supported_scheme_ids: list[str] = []
    notes: str = Field("", max_length=300)
    website_url: str = Field(max_length=500)
    verified: bool = False

    @field_validator("state", "district", "latitude", "longitude", mode="before")
    @classmethod
    def _blank(cls, v):
        return _blank_to_none(v)

    @field_validator("state")
    @classmethod
    def _all_states(cls, v):
        return None if v in (None, "All States") else v

    @field_validator("website_url")
    @classmethod
    def _url(cls, v):
        if not URL_RE.match(v):
            raise ValueError("website_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _coords(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class PartnerOut(ORM):
    id: str
    name: str
    partner_type: str
    state: str | None
    district: str | None
    latitude: float | None
    longitude: float | None
    coverage: str
    supported_scheme_ids: list[str]
    notes: str
    website_url: str
    verified: bool
    distance_km: float | None = None  # only set by /partners/nearby


# --------------------------------------------------------------------------- applications
class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scheme_id: str = Field(min_length=1, max_length=64)
    application_reference: str | None = Field(None, max_length=100)

    @field_validator("application_reference", mode="before")
    @classmethod
    def _blank(cls, v):
        return _blank_to_none(v)


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str | None = None
    application_reference: str | None = Field(None, max_length=100)

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        return _one_of(v, tuple(C.APPLICATION_STATUSES), "status")

    @field_validator("application_reference", mode="before")
    @classmethod
    def _blank(cls, v):
        return _blank_to_none(v)


class ApplicationOut(BaseModel):
    id: str
    scheme_id: str
    scheme_name: str
    application_reference: str | None
    status: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- readiness / tools
class ReadinessItemOut(CheckOut):
    category: str | None = None


class ReadinessCategoryOut(BaseModel):
    key: str
    label: str
    max_score: int
    score: int
    items: list[CheckOut]


class TopSchemeOut(BaseModel):
    scheme_id: str
    name: str
    description: str
    eligibility_status: Literal["eligible", "potentially_eligible", "not_eligible"]
    match_pct: int


class ReadinessOut(BaseModel):
    overall: int
    top_scheme: TopSchemeOut | None
    categories: list[ReadinessCategoryOut]
    strengths: list[ReadinessItemOut]
    gaps: list[ReadinessItemOut]


class EmiIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_amount: float = Field(ge=0, le=100_000_000_000)
    own_contribution: float = Field(0, ge=0, le=100_000_000_000)
    subsidy: float = Field(0, ge=0, le=100_000_000_000)
    interest_rate: float = Field(10, ge=0, le=100)          # % per year
    tenure_years: float = Field(5, ge=0, le=50)
    moratorium_months: float = Field(0, ge=0, le=120)


class EmiOut(BaseModel):
    net_loan_amount: float
    monthly_emi: float
    total_repayment: float
    total_interest: float
    moratorium_months: float


class WhatIfIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funding_required: float = Field(ge=0, le=100_000_000_000)
    own_contribution: float = Field(0, ge=0, le=100_000_000_000)
    interest_rate: float = Field(10, ge=0, le=100)
    tenure_years: float = Field(5, ge=0, le=50)
    moratorium_months: float = Field(0, ge=0, le=120)


class ScenarioOut(BaseModel):
    funding_required: float
    own_contribution: float
    loan_portion: float
    interest_rate: float
    tenure_years: float
    emi: float
    total_repayment: float
    funding_gap: float
    top_scheme_id: str | None
    top_scheme_name: str | None
    eligibility_status: str | None


class WhatIfOut(BaseModel):
    current: ScenarioOut
    what_if: ScenarioOut


class FundingStepOut(BaseModel):
    source: Literal["scheme", "own_contribution"]
    scheme_id: str | None
    scheme_name: str | None
    eligibility_status: str | None
    amount: float
    reason: str


class FundingPathOut(BaseModel):
    total: float
    steps: list[FundingStepOut]
    gap: float
