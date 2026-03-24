from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, desc, select

from app.config import settings
from app.db import get_db
from app.models import (
    DailyPass,
    PaymentStatus,
    QrToken,
    ReservationStatus,
    TokenStatus,
    OneTimeToken,
    OneTimeTokenStatus,
)
from app.qr_helpers import create_or_rotate_token
from app.services.auth_service import get_passenger_from_token
from fastapi import Response
from app.qr_helpers import make_qr_png


router = APIRouter(prefix="/app/qr", tags=["App QR"])

security = HTTPBearer()


def _get_active_monthly_qr(db, passenger_id):
    stmt = (
        select(QrToken)
        .where(
            and_(
                QrToken.passenger_id == passenger_id,
                QrToken.status == TokenStatus.ACTIVE,
            )
        )
        .order_by(desc(QrToken.valid_to), desc(QrToken.id))
    )
    return db.execute(stmt).scalars().first()


def _get_today_confirmed_daily_pass(db, passenger_id, today: date):
    stmt = (
        select(DailyPass)
        .where(
            and_(
                DailyPass.passenger_id == passenger_id,
                DailyPass.service_date == today,
                DailyPass.payment_status == PaymentStatus.PAGADO,
                DailyPass.reservation_status == ReservationStatus.CONFIRMADO,
                DailyPass.is_deleted == False,
            )
        )
        .order_by(desc(DailyPass.id))
    )
    return db.execute(stmt).scalars().first()


def _get_active_one_time_token_for_daily_pass(db, daily_pass_id):
    stmt = (
        select(OneTimeToken)
        .where(
            and_(
                OneTimeToken.daily_pass_id == daily_pass_id,
                OneTimeToken.status == OneTimeTokenStatus.ACTIVE,
                OneTimeToken.used_at.is_(None),
            )
        )
        .order_by(desc(OneTimeToken.id))
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
def get_my_qr_bundle(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    today = date.today()

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        # QR mensual
        monthly_qr = _get_active_monthly_qr(db, passenger.id)

        if not monthly_qr:
            create_or_rotate_token(db, passenger.id)
            monthly_qr = _get_active_monthly_qr(db, passenger.id)

        monthly_qr_data = {
            "available": False,
            "token": None,
            "status": None,
            "valid_from": None,
            "valid_to": None,
            "qr_url": None,
        }

        if monthly_qr:
            monthly_qr_data = {
                "available": True,
                "token": monthly_qr.token,
                "status": monthly_qr.status.value,
                "valid_from": monthly_qr.valid_from,
                "valid_to": monthly_qr.valid_to,
                "qr_url": f"{settings.public_base_url.rstrip('/')}/q/{monthly_qr.token}",
                "image_url": f"{settings.public_base_url.rstrip('/')}/app/qr/monthly/image",
            }

        # QR pase diario
        daily_pass = _get_today_confirmed_daily_pass(db, passenger.id, today)

        daily_pass_qr_data = {
            "available": False,
            "daily_pass_id": None,
            "service_date": None,
            "trip_type": None,
            "token": None,
            "status": None,
            "qr_url": None,
        }

        if daily_pass:
            ot = _get_active_one_time_token_for_daily_pass(db, daily_pass.id)

            if ot:
                daily_pass_qr_data = {
                    "available": True,
                    "daily_pass_id": daily_pass.id,
                    "service_date": daily_pass.service_date,
                    "trip_type": daily_pass.trip_type.value,
                    "token": ot.token,
                    "status": ot.status.value,
                    "qr_url": f"{settings.public_base_url.rstrip('/')}/ot/{ot.token}",
                    "image_url": f"{settings.public_base_url.rstrip('/')}/app/qr/daily-pass/image",
                }

        return {
            "passenger": {
                "id": str(passenger.id),
                "full_name": passenger.full_name,
            },
            "monthly_qr": monthly_qr_data,
            "daily_pass_qr": daily_pass_qr_data,
        }

@router.get("/monthly/image", dependencies=[Depends(security)])
def get_monthly_qr_image(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        monthly_qr = _get_active_monthly_qr(db, passenger.id)

        if not monthly_qr:
            create_or_rotate_token(db, passenger.id)
            monthly_qr = _get_active_monthly_qr(db, passenger.id)

        if not monthly_qr:
            raise HTTPException(status_code=500, detail="No fue posible obtener QR mensual")

        qr_url = f"{settings.public_base_url.rstrip('/')}/q/{monthly_qr.token}"
        png_bytes = make_qr_png(qr_url)

        return Response(content=png_bytes, media_type="image/png")

@router.get("/daily-pass/image", dependencies=[Depends(security)])
def get_daily_pass_qr_image(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    today = date.today()

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        daily_pass = _get_today_confirmed_daily_pass(db, passenger.id, today)
        if not daily_pass:
            raise HTTPException(status_code=404, detail="No existe pase diario confirmado para hoy")

        ot = _get_active_one_time_token_for_daily_pass(db, daily_pass.id)
        if not ot:
            raise HTTPException(status_code=404, detail="No existe QR activo para el pase diario")

        qr_url = f"{settings.public_base_url.rstrip('/')}/ot/{ot.token}"
        png_bytes = make_qr_png(qr_url)

        return Response(content=png_bytes, media_type="image/png")
