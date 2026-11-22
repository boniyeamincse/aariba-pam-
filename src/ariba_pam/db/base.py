"""SQLAlchemy base and declarative configuration."""

from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is timezone-aware in UTC (normalizes naive SQLite datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_id(prefix: str = "") -> str:
    """Generate prefixed opaque identifier."""
    uid = uuid.uuid4().hex[:16]
    return f"{prefix}_{uid}" if prefix else uid


class Base(DeclarativeBase):
    """Base declarative class for all models."""
    pass
