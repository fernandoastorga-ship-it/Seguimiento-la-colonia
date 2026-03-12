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

SessionLocal = sessionmaker(
    bind=ENGINE,
    autoflush=False,
    autocommit=False,
    future=True,
    expire_on_commit=False,  # evita DetachedInstanceError en admin
)


def _exec_autocommit(stmts: list[str], warn_prefix: str) -> None:
    try:
        with ENGINE.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as e:
        print(f"WARN: {warn_prefix}:", repr(e))


def _get_udt_name(table: str, column: str, schema: str = "public") -> str | None:
    """
    Devuelve el nombre real del tipo (udt_name) que usa una columna.
    Para enums en Postgres, udt_name suele ser el nombre del TYPE.
    """
    try:
        with ENGINE.connect() as conn:
            res = conn.execute(
                text(
                    """
                    SELECT udt_name
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = :table
                      AND column_name = :column
                    LIMIT 1
                    """
                ),
                {"schema": schema, "table": table, "column": column},
            ).fetchone()
            return res[0] if res else None
    except Exception as e:
        print("WARN: _get_udt_name failed:", repr(e))
        return None


def _ensure_enum_values(enum_type_name: str, values: list[str]) -> None:
    stmts = [f"ALTER TYPE {enum_type_name} ADD VALUE IF NOT EXISTS '{v}';" for v in values]
    _exec_autocommit(stmts, f"_ensure_enum_values failed for {enum_type_name}")


def _ensure_plan_enum_values() -> None:
    # tu enum de planes (puede llamarse 'plantype' o 'plan_type_enum' según historia)
    for enum_name in ["plantype", "plan_type_enum"]:
        _ensure_enum_values(enum_name, ["VIAJES_10", "VIAJES_20", "VIAJES_30", "VIAJES_40"])


def _ensure_pickup_point_enum_values() -> None:
    """
    Asegura que el enum real usado por:
      - passengers.pickup_point_default
      - checkins.pickup_point
    contenga LA_MONEDA, etc.
    """
    values = ["LA_COLONIA", "CRUCE_MALLOCO", "LA_MONEDA"]

    # 1) Descubrir por columna (la forma correcta)
    udt_passengers = _get_udt_name("passengers", "pickup_point_default")
    if udt_passengers:
        _ensure_enum_values(udt_passengers, values)

    udt_checkins = _get_udt_name("checkins", "pickup_point")
    if udt_checkins:
        _ensure_enum_values(udt_checkins, values)

    # 2) Fallback por si information_schema no devuelve (raro, pero posible)
    for enum_name in ["pickup_point_enum", "pickup_point"]:
        _ensure_enum_values(enum_name, values)


def _migrate_old_subscription_plan_values() -> None:
    """
    Migra planes antiguos a VIAJES_* según regla:
      - IDA o VUELTA  -> VIAJES_20
      - IDA_VUELTA    -> VIAJES_40
      - otros -> por rides_included, default VIAJES_20
    (castea a ::plantype porque la columna es ENUM)
    """
    stmts = [
        """
        UPDATE subscriptions
        SET plan_type =
            (
              CASE
                WHEN plan_type::text IN ('IDA', 'VUELTA') THEN 'VIAJES_20'
                WHEN plan_type::text = 'IDA_VUELTA' THEN 'VIAJES_40'
                WHEN rides_included = 10 THEN 'VIAJES_10'
                WHEN rides_included = 20 THEN 'VIAJES_20'
                WHEN rides_included = 30 THEN 'VIAJES_30'
                WHEN rides_included = 40 THEN 'VIAJES_40'
                ELSE 'VIAJES_20'
              END
            )::plantype
        WHERE plan_type::text NOT IN ('VIAJES_10','VIAJES_20','VIAJES_30','VIAJES_40');
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
