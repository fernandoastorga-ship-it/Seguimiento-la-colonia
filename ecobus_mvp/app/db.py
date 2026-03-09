from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from .config import settings


def _normalize_db_url(url: str) -> str:
    # Render usually provides DATABASE_URL as postgres://...; SQLAlchemy expects postgresql+psycopg2://
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


ENGINE = create_engine(
    _normalize_db_url(settings.database_url),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)


def _ensure_plan_enum_values() -> None:
    """
    Fix for Postgres enum already created as 'plantype' without the new ride-pack values.
    Runs on import in both API and Admin.
    """
    stmts = [
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_10';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_20';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_30';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_40';",
    ]

    try:
        # ALTER TYPE requires AUTOCOMMIT in Postgres
        with ENGINE.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as e:
        # Don't crash the app; log and continue.
        print("WARN: _ensure_plan_enum_values failed:", repr(e))


# Run at import time (API + Admin)
_ensure_plan_enum_values()


@contextmanager
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
