"""Database engine, session management, and dependencies."""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ariba_pam.config import settings
from ariba_pam.db.base import Base

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI database dependency yielding an isolated transactional session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables in the connected database."""
    # Import all models to ensure registration with Base
    import ariba_pam.db.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
