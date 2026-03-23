import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está definida")

engine = create_engine(DATABASE_URL)

SQL_STATEMENTS = [
    """
    ALTER TABLE passengers
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS accepted_terms_version VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS accepted_terms_at TIMESTAMP NULL;
    """,
    """
    DROP TABLE IF EXISTS otp_codes CASCADE;
    """,
    """
    DROP TABLE IF EXISTS user_sessions CASCADE;
    """,
    """
    CREATE TABLE IF NOT EXISTS otp_codes (
        id SERIAL PRIMARY KEY,
        passenger_id UUID NULL REFERENCES passengers(id),
        identifier VARCHAR(200) NOT NULL,
        channel VARCHAR(20) NOT NULL,
        code_hash VARCHAR(255) NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        consumed_at TIMESTAMP NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_otp_codes_passenger_id ON otp_codes(passenger_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_otp_codes_identifier ON otp_codes(identifier);
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id SERIAL PRIMARY KEY,
        passenger_id UUID NOT NULL REFERENCES passengers(id),
        token_hash VARCHAR(255) NOT NULL UNIQUE,
        expires_at TIMESTAMP NOT NULL,
        revoked_at TIMESTAMP NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        device_info TEXT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_user_sessions_passenger_id ON user_sessions(passenger_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash ON user_sessions(token_hash);
    """,
]

with engine.begin() as conn:
    for stmt in SQL_STATEMENTS:
        conn.execute(text(stmt))

print("Migración auth ejecutada correctamente.")
