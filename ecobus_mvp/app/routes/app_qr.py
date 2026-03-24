from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, select

from app.config import settings
from app.db import get_db
from app.models import QrToken, TokenStatus
from app.qr_helpers import make_qr_png, create_or_rotate_token
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/qr", tags=["App QR"])

security = HTTPBearer()


def _get_current_passenger(credentials: HTTPAuthorizationCredentials):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return passenger


def _get_active_qr_token(db, passenger_id):
    stmt = (
        select(QrToken)
        .where(
            and_(
                QrToken.passenger_id == passenger_id,
                QrToken.status == TokenStatus.ACTIVE,
            )
        )
        .order_by(QrToken.valid_to.desc(), QrToken.id.desc())
    )
    return db.execute(stmt).scalars().first()


@router.get("/health")
def qr_health():
    return {
        "ok": True,
        "module": "app_qr",
        "message": "Módulo QR operativo",
    }


@router.get("/", dependencies=[Depends(security)])
def get_my_qr(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        qr_token = _get_active_qr_token(db, passenger.id)

        # fallback seguro: si por alguna razón no tiene token activo, lo generamos
        if not qr_token:
            raw_token = create_or_rotate_token(db, passenger.id)
            qr_token = _get_active_qr_token(db, passenger.id)
            if not qr_token:
                raise HTTPException(status_code=500, detail="No fue posible generar QR activo")
        else:
            raw_token = qr_token.token

        qr_url = f"{settings.public_base_url.rstrip('/')}/q/{raw_token}"
        image_url = f"{settings.public_base_url.rstrip('/')}/app/qr/image"

        return {
            "passenger_id": str(passenger.id),
            "full_name": passenger.full_name,
            "token": raw_token,
            "status": qr_token.status.value,
            "valid_from": qr_token.valid_from,
            "valid_to": qr_token.valid_to,
            "qr_url": qr_url,
            "image_url": image_url,
        }


@router.get("/image", dependencies=[Depends(security)])
def get_my_qr_image(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        qr_token = _get_active_qr_token(db, passenger.id)

        if not qr_token:
            raw_token = create_or_rotate_token(db, passenger.id)
        else:
            raw_token = qr_token.token

        qr_url = f"{settings.public_base_url.rstrip('/')}/q/{raw_token}"
        png_bytes = make_qr_png(qr_url)

        return Response(content=png_bytes, media_type="image/png")
