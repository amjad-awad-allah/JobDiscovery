"""SQLAlchemy 2.x models for Company & Job Discovery."""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class Company(Base):
    """Company information discovered from website and Impressum."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    website_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    impressum_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    house_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fax: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    register_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    register_court: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    persons: Mapped[List["CompanyPerson"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["JobPosting"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}', domain='{self.domain}')>"


class CompanyPerson(Base):
    """Company representative or managing director."""
    __tablename__ = "company_persons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)

    company: Mapped["Company"] = relationship(back_populates="persons")

    def __repr__(self) -> str:
        return f"<CompanyPerson(id={self.id}, name='{self.first_name or ''} {self.last_name}', role='{self.role}')>"


class JobPosting(Base):
    """Job advertisement discovered on company career pages."""
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "url", name="uq_company_job_url"),
    )

    def __repr__(self) -> str:
        return f"<JobPosting(id={self.id}, title='{self.title}', url='{self.url}')>"

    company: Mapped["Company"] = relationship(back_populates="jobs")

