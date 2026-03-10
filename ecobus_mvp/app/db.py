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


def _exec_autocommit(stmts: list[str], warn_prefix: str) -> None:
    try:
        with ENGINE.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as e:
        print(f"WARN: {warn_prefix}:", repr(e))


def _ensure_plan_enum_values() -> None:
    """
    Ensures Postgres enum 'plantype' contains the new ride-pack values.
    Runs on import in both API and Admin.
    """
    stmts = [
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_10';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_20';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_30';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_40';",
    ]
    _exec_autocommit(stmts, "_ensure_plan_enum_values failed")


def _ensure_pickup_point_enum_values() -> None:
    """
    Ensures Postgres enum 'pickup_point_enum' contains current pickup points.
    Add/remove values here to match app.models.PickupPoint.
    """
    stmts = [
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'LA_COLONIA';",
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'CRUCE_MALLOCO';",
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'LA_MONEDA';",
        # If you truly use these in your PickupPoint enum, keep them; otherwise remove.
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'PLAZA_PENAFOR';",
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'METRO_LO_VALLEDOR';",
        "ALTER TYPE pickup_point_enum ADD VALUE IF NOT EXISTS 'METRO_LA_MONEDA';",
    ]
    _exec_autocommit(stmts, "_ensure_pickup_point_enum_values failed")


def _migrate_old_subscription_plan_values() -> None:
    """
    Migra planes antiguos a VIAJES_* según tu regla:
      - IDA o VUELTA  -> VIAJES_20
      - IDA_VUELTA    -> VIAJES_40
      - Cualquier otro no VIAJES_* -> si rides_included calza 10/20/30/40 usa eso, si no -> VIAJES_20
    """
    stmts = [
        """
        UPDATE subscriptions
        SET plan_type =
            CASE
              WHEN plan_type::text IN ('IDA', 'VUELTA') THEN 'VIAJES_20'
              WHEN plan_type::text = 'IDA_VUELTA' THEN 'VIAJES_40'
              WHEN rides_included = 10 THEN 'VIAJES_10'
              WHEN rides_included = 20 THEN 'VIAJES_20'
              WHEN rides_included = 30 THEN 'VIAJES_30'
              WHEN rides_included = 40 THEN 'VIAJES_40'
              ELSE 'VIAJES_20'
            END
        WHERE plan_type::text NOT LIKE 'VIAJES_%';
        """
    ]
    _exec_autocommit(stmts, "_migrate_old_subscription_plan_values failed")


# Run at import time (API + Admin) - order matters
_ensure_plan_enum_values()
_ensure_pickup_point_enum_values()
_migrate_old_subscription_plan_values()


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
