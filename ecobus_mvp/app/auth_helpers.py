from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.models import Passenger, UserSession


security = HTTPBearer()


def get_passenger_from_token(db: Session, token: str) -> Passenger:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    user_session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.utcnow(),
        )
        .first()
    )

    if not user_session:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    passenger = (
        db.query(Passenger)
        .filter(
            Passenger.id == user_session.passenger_id,
            Passenger.is_deleted == False,
            Passenger.is_active == True,
        )
        .first()
    )

    if not passenger:
        raise HTTPException(status_code=401, detail="Pasajero no disponible")

    return passenger
