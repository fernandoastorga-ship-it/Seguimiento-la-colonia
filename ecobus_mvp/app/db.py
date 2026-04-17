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
    for enum_name in ["pickup_point_enum"]:
        _ensure_enum_values(enum_name, values)

def _ensure_one_time_token_enum_values() -> None:
    # Por si el TYPE no existe aún, este ALTER fallará; lo dejamos como best-effort.
    _ensure_enum_values("one_time_token_status_enum", ["ACTIVE", "USED", "REVOKED"])



def _ensure_service_enum_values() -> None:
    _ensure_enum_values("service_code_enum", ["LA_COLONIA", "ALTUE"])

def _ensure_checkins_entitlement_column() -> None:
    stmts = [
        "ALTER TABLE checkins ADD COLUMN IF NOT EXISTS entitlement varchar(20);"
    ]
    _exec_autocommit(stmts, "_ensure_checkins_entitlement_column failed")

def _ensure_one_time_tokens_schema() -> None:
    stmts = [
        # Si la tabla ya existe, agrega la columna faltante
        "ALTER TABLE one_time_tokens ADD COLUMN IF NOT EXISTS daily_pass_id integer;",
        # Índice (opcional pero recomendado)
        "CREATE INDEX IF NOT EXISTS ix_one_time_tokens_daily_pass_id ON one_time_tokens(daily_pass_id);",
    ]
    _exec_autocommit(stmts, "_ensure_one_time_tokens_schema failed")

def _ensure_soft_delete_columns() -> None:
    stmts = [
        "ALTER TABLE passengers ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;",
        "ALTER TABLE passengers ADD COLUMN IF NOT EXISTS deleted_at timestamp NULL;",
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;",
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS deleted_at timestamp NULL;",
        "ALTER TABLE daily_passes ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;",
        "ALTER TABLE daily_passes ADD COLUMN IF NOT EXISTS deleted_at timestamp NULL;",
    ]
    _exec_autocommit(stmts, "_ensure_soft_delete_columns failed")

_ensure_soft_delete_columns()

def _ensure_services_schema() -> None:
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_services_code ON services(code);",

        "ALTER TABLE passengers ADD COLUMN IF NOT EXISTS service_id integer NULL;",
        "CREATE INDEX IF NOT EXISTS ix_passengers_service_id ON passengers(service_id);",

        "ALTER TABLE checkins ADD COLUMN IF NOT EXISTS service_id integer NULL;",
        "CREATE INDEX IF NOT EXISTS ix_checkins_service_id ON checkins(service_id);",
    ]
    _exec_autocommit(stmts, "_ensure_services_schema failed")

def _seed_default_services() -> None:
    stmts = [
        """
        INSERT INTO services (code, name, is_active)
        VALUES ('LA_COLONIA', 'La Colonia', TRUE)
        ON CONFLICT (code) DO NOTHING;
        """,
        """
        INSERT INTO services (code, name, is_active)
        VALUES ('ALTUE', 'Altue', TRUE)
        ON CONFLICT (code) DO NOTHING;
        """,
    ]
    _exec_autocommit(stmts, "_seed_default_services failed")

def _ensure_vehicle_locations_schema() -> None:
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS vehicle_locations (
            id SERIAL PRIMARY KEY,
            service_id integer NOT NULL REFERENCES services(id),
            lat DOUBLE PRECISION NOT NULL,
            lng DOUBLE PRECISION NOT NULL,
            source VARCHAR(50) NULL,
            recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_vehicle_locations_service_id ON vehicle_locations(service_id);",
        "CREATE INDEX IF NOT EXISTS ix_vehicle_locations_recorded_at ON vehicle_locations(recorded_at);",
    ]
    _exec_autocommit(stmts, "_ensure_vehicle_locations_schema failed")

def _backfill_service_ids() -> None:
    stmts = [
        """
        UPDATE passengers p
        SET service_id = s.id
        FROM services s
        WHERE p.service_id IS NULL
          AND s.code = 'LA_COLONIA';
        """,
        """
        UPDATE checkins c
        SET service_id = p.service_id
        FROM passengers p
        WHERE c.passenger_id = p.id
          AND c.service_id IS NULL
          AND p.service_id IS NOT NULL;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_name = 'passengers'
                  AND constraint_name = 'fk_passengers_service_id'
            ) THEN
                ALTER TABLE passengers
                ADD CONSTRAINT fk_passengers_service_id
                FOREIGN KEY (service_id) REFERENCES services(id);
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_name = 'checkins'
                  AND constraint_name = 'fk_checkins_service_id'
            ) THEN
                ALTER TABLE checkins
                ADD CONSTRAINT fk_checkins_service_id
                FOREIGN KEY (service_id) REFERENCES services(id);
            END IF;
        END $$;
        """,
    ]
    _exec_autocommit(stmts, "_backfill_service_ids failed")


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
_ensure_one_time_token_enum_values()
_ensure_checkins_entitlement_column()
_migrate_old_subscription_plan_values()
_ensure_one_time_tokens_schema()
_ensure_service_enum_values()
_ensure_services_schema()
_seed_default_services()
_backfill_service_ids()
_ensure_vehicle_locations_schema()


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
