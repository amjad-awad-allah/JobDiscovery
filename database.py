"""SQLite database operations and persistence for Company Discovery."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base, Company, CompanyPerson, JobPosting, utc_now

DEFAULT_DB_PATH = "company_discovery.db"


def get_engine(db_path: str = DEFAULT_DB_PATH) -> Engine:
    """Create and return a SQLAlchemy SQLite engine."""
    # check_same_thread=False allows SQLite to be used across threads if needed
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(db_path: str = DEFAULT_DB_PATH) -> Engine:
    """Initialize database tables according to declared models."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine_or_path: Engine | str = DEFAULT_DB_PATH) -> Session:
    """Provide a new SQLAlchemy session."""
    if isinstance(engine_or_path, Engine):
        engine = engine_or_path
    else:
        engine = get_engine(engine_or_path)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def save_or_update_company(
    session: Session,
    company_data: Dict[str, Any],
    persons_data: Optional[List[Dict[str, str]]] = None,
) -> Tuple[Company, bool]:
    """
    Save a new company or update an existing company identified by domain.
    
    Returns:
        (company, is_created)
    """
    domain = company_data.get("domain", "").strip().lower()
    if not domain:
        raise ValueError("A valid domain is required to store a company.")

    stmt = select(Company).where(Company.domain == domain)
    company = session.execute(stmt).scalar_one_or_none()

    now = utc_now()
    is_created = False

    if company is None:
        # Create new company record
        company = Company(
            domain=domain,
            website_url=company_data.get("website_url", ""),
            name=company_data.get("name"),
            legal_form=company_data.get("legal_form"),
            impressum_url=company_data.get("impressum_url"),
            street=company_data.get("street"),
            house_number=company_data.get("house_number"),
            postal_code=company_data.get("postal_code"),
            city=company_data.get("city"),
            country=company_data.get("country"),
            email=company_data.get("email"),
            phone=company_data.get("phone"),
            fax=company_data.get("fax"),
            vat_id=company_data.get("vat_id"),
            register_number=company_data.get("register_number"),
            register_court=company_data.get("register_court"),
            created_at=now,
            updated_at=now,
        )
        session.add(company)
        session.flush()  # To assign company.id
        is_created = True
    else:
        # Update existing company record with non-null extracted fields
        for field, value in company_data.items():
            if field in ("id", "domain", "created_at"):
                continue
            if value is not None and str(value).strip() != "":
                setattr(company, field, value)
        company.updated_at = now
        session.flush()

    # Synchronize company persons
    if persons_data is not None:
        normalized_new = []
        for p_data in persons_data:
            last_name = p_data.get("last_name", "").strip()
            role = p_data.get("role", "Representative").strip()
            first_name = p_data.get("first_name", "").strip() or None
            if last_name:
                normalized_new.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": role,
                })

        # Remove existing persons who are NOT in the new extracted list
        for existing in list(company.persons):
            matched = any(
                existing.last_name.lower() == p["last_name"].lower()
                and (existing.first_name or "").lower() == (p["first_name"] or "").lower()
                for p in normalized_new
            )
            if not matched:
                session.delete(existing)

        # Update existing persons or add new ones
        for p in normalized_new:
            existing_p = next(
                (
                    ep for ep in company.persons
                    if ep.last_name.lower() == p["last_name"].lower()
                    and (ep.first_name or "").lower() == (p["first_name"] or "").lower()
                ),
                None,
            )
            if existing_p:
                existing_p.role = p["role"]
            else:
                new_person = CompanyPerson(
                    company_id=company.id,
                    first_name=p["first_name"],
                    last_name=p["last_name"],
                    role=p["role"],
                )
                session.add(new_person)

    session.commit()
    return company, is_created


class JobSyncResult(tuple):
    """
    Tuple representing (created_count, updated_count) with an optional deleted attribute.
    Maintains complete backwards compatibility with tuple unpacking:
        created, updated = save_or_update_jobs(...)
    """
    def __new__(cls, created: int, updated: int, deleted: int = 0):
        return super().__new__(cls, (created, updated))

    def __init__(self, created: int, updated: int, deleted: int = 0):
        self.created = created
        self.updated = updated
        self.deleted = deleted


def save_or_update_jobs(
    session: Session,
    company_id: int,
    jobs_data: List[Dict[str, Any]],
    prune_missing: bool = False,
) -> Tuple[int, int]:
    """
    Save or update discovered job postings for a company.
    
    Prevents duplicate job listings using (company_id, normalized_url).
    Preserves original first_seen_at and updates last_seen_at.
    If prune_missing is True, any existing job for this company that does not
    appear in jobs_data is deleted from the database.
    
    Returns:
        JobSyncResult(created_count, updated_count, deleted_count)
    """
    created_count = 0
    updated_count = 0
    deleted_count = 0
    now = utc_now()
    active_urls = set()

    for job in jobs_data:
        raw_url = job.get("url", "").strip()
        title = job.get("title", "").strip()
        if not raw_url or not title:
            continue

        active_urls.add(raw_url)

        stmt = select(JobPosting).where(
            JobPosting.company_id == company_id,
            JobPosting.url == raw_url,
        )
        existing_job = session.execute(stmt).scalar_one_or_none()

        if existing_job is None:
            # Create new job listing
            new_job = JobPosting(
                company_id=company_id,
                title=title,
                url=raw_url,
                location=job.get("location"),
                employment_type=job.get("employment_type"),
                description=job.get("description"),
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(new_job)
            created_count += 1
        else:
            # Update existing job: update metadata and last_seen_at, retain first_seen_at
            if title:
                existing_job.title = title
            if job.get("location"):
                existing_job.location = job.get("location")
            if job.get("employment_type"):
                existing_job.employment_type = job.get("employment_type")
            if job.get("description"):
                existing_job.description = job.get("description")
            existing_job.last_seen_at = now
            updated_count += 1

    if prune_missing:
        # Delete old jobs for this company that no longer appear in jobs_data
        stmt_existing = select(JobPosting).where(JobPosting.company_id == company_id)
        existing_db_jobs = list(session.execute(stmt_existing).scalars().all())
        for old_job in existing_db_jobs:
            if old_job.url not in active_urls:
                session.delete(old_job)
                deleted_count += 1

    session.commit()
    return JobSyncResult(created_count, updated_count, deleted_count)


def delete_company(session: Session, company_id: int) -> bool:
    """Delete a company and cascade-delete all its associated persons and jobs."""
    company = get_company_by_id(session, company_id)
    if not company:
        return False
    session.delete(company)
    session.commit()
    return True


def get_company_by_query(session: Session, query: str) -> Optional[Company]:
    """Search for a company by URL, domain, or name."""
    clean_q = query.strip()
    if not clean_q:
        return None

    from crawler import normalize_domain

    # 1. Match by normalized domain
    domain = normalize_domain(clean_q)
    if domain:
        stmt = select(Company).where(Company.domain == domain)
        company = session.execute(stmt).scalar_one_or_none()
        if company:
            return company

    # 2. Match substring in domain, website_url, or name
    stmt = select(Company).where(
        (Company.domain.ilike(f"%{clean_q}%"))
        | (Company.website_url.ilike(f"%{clean_q}%"))
        | (Company.name.ilike(f"%{clean_q}%"))
    )
    return session.execute(stmt).scalars().first()


def get_all_companies(session: Session) -> List[Company]:
    """Retrieve all companies ordered by ID."""
    stmt = select(Company).order_by(Company.id)
    return list(session.execute(stmt).scalars().all())


def get_company_by_id(session: Session, company_id: int) -> Optional[Company]:
    """Retrieve a company by its primary key ID."""
    stmt = select(Company).where(Company.id == company_id)
    return session.execute(stmt).scalar_one_or_none()


def get_database_stats(session: Session) -> Dict[str, int]:
    """Return summary counts of companies, jobs, and representatives."""
    from sqlalchemy import func

    companies_count = session.scalar(select(func.count()).select_from(Company)) or 0
    jobs_count = session.scalar(select(func.count()).select_from(JobPosting)) or 0
    persons_count = session.scalar(select(func.count()).select_from(CompanyPerson)) or 0

    return {
        "companies": companies_count,
        "jobs": jobs_count,
        "persons": persons_count,
    }


def get_all_jobs(session: Session) -> List[JobPosting]:
    """Retrieve all job postings across all companies."""
    stmt = select(JobPosting).order_by(JobPosting.company_id, JobPosting.id)
    return list(session.execute(stmt).scalars().all())



