import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import UserSession, Passenger


SESSION_EXP_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, passenger: Passenger, device_info: str | None = None) -> tuple[str, int]:
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_EXP_DAYS)

    session = UserSession(
        passenger_id=passenger.id,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
        device_info=device_info,
    )
    db.add(session)

    passenger.last_login_at = datetime.utcnow()

    db.commit()

    return raw_token, SESSION_EXP_DAYS * 24 * 60 * 60


def get_passenger_from_token(db: Session, token: str) -> Passenger | None:
    token_hash = _hash_token(token)

    session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.utcnow(),
        )
        .first()
    )

    if not session:
        return None

    passenger = (
        db.query(Passenger)
        .filter(
            Passenger.id == session.passenger_id,
            Passenger.is_deleted == False,
        )
        .first()
    )

    return passenger


def revoke_session(db: Session, token: str) -> bool:
    token_hash = _hash_token(token)

    session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )

    if not session:
        return False

    session.revoked_at = datetime.utcnow()
    db.commit()
    return True
