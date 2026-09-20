import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """Always store and return timezone-aware UTC (SQLite would otherwise drop the tzinfo,
    and the API would emit ambiguous timestamps without a 'Z')."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    profile: Mapped["Profile | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    documents: Mapped[list["Document"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    """One row per entrepreneur. Numeric fields are real numbers, not strings."""
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(100))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(16))
    state: Mapped[str | None] = mapped_column(String(50))
    district: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(16))
    occupation: Mapped[str | None] = mapped_column(String(100))
    business_type: Mapped[str | None] = mapped_column(String(40))
    business_stage: Mapped[str | None] = mapped_column(String(40))
    annual_income: Mapped[float | None] = mapped_column(Float)
    annual_turnover: Mapped[float | None] = mapped_column(Float)
    funding_required: Mapped[float | None] = mapped_column(Float)
    own_contribution: Mapped[float | None] = mapped_column(Float)
    funding_purpose: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class Scheme(Base):
    """Fixed scheme schema -- the same shape is used by the seed data, the API and the admin form."""
    __tablename__ = "schemes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)          # slug, e.g. "pmegp"
    name: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    scheme_type: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    min_amount: Mapped[float] = mapped_column(Float)
    max_amount: Mapped[float] = mapped_column(Float)
    eligible_categories: Mapped[list] = mapped_column(JSON, default=list)
    business_types: Mapped[list] = mapped_column(JSON, default=list)
    business_stages: Mapped[list] = mapped_column(JSON, default=list)
    min_age: Mapped[int] = mapped_column(Integer, default=18)
    max_income: Mapped[float | None] = mapped_column(Float)                # None = no personal income limit
    education: Mapped[str] = mapped_column(String(300), default="")
    purpose: Mapped[str] = mapped_column(String(300), default="")
    interest_rate: Mapped[str] = mapped_column(String(300), default="")
    own_contribution_pct: Mapped[float] = mapped_column(Float, default=0.10)  # 0.10 == 10 %
    application_channel: Mapped[str] = mapped_column(String(300), default="")
    required_documents: Mapped[list] = mapped_column(JSON, default=list)   # document-type slugs
    benefits: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(200), default="")
    official_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)


class Document(Base):
    """Metadata only -- the bytes live on disk (or object storage) under `stored_path`."""
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "document_type", name="uq_document_user_type"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(50))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(300))                   # relative to upload_dir
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="documents")


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150))
    partner_type: Mapped[str] = mapped_column(String(80), default="Partner")
    state: Mapped[str | None] = mapped_column(String(50), index=True)       # None = pan-India
    district: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[str] = mapped_column(String(200), default="")
    supported_scheme_ids: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(String(300), default="")
    website_url: Mapped[str] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scheme_id: Mapped[str] = mapped_column(ForeignKey("schemes.id"))
    application_reference: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), default="documents_pending")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="applications")
    scheme: Mapped[Scheme] = relationship()
