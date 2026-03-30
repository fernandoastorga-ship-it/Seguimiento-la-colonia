from __future__ import annotations
import json
import uuid
from datetime import datetime, date
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.options import WebpayOptions
from transbank.common.integration_type import IntegrationType
import uuid
from datetime import datetime, date
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime


def _uuid_col():
    # Works for Postgres and falls back to string for SQLite.
    try:
        return PG_UUID(as_uuid=True)
    except Exception:
        return String(36)

def get_webpay_options():
    import os

    commerce_code = os.getenv("TBK_COMMERCE_CODE", "597055555532")
    api_key = os.getenv("TBK_API_KEY", "597055555532")
    env = os.getenv("TBK_ENV", "integration").lower()

    integration_type = (
        IntegrationType.TEST if env == "integration" else IntegrationType.LIVE
    )

    return WebpayOptions(commerce_code, api_key, integration_type)

class MonthlyPlanCheckoutIn(BaseModel):
    month: date
    plan_type: str


class DailyPassCheckoutIn(BaseModel):
    service_date: date
    trip_type: str

class Base(DeclarativeBase):
    pass


class PickupPoint(str, PyEnum):
    LA_COLONIA = "LA_COLONIA"
    CRUCE_MALLOCO = "CRUCE_MALLOCO"
    LA_MONEDA = "LA_MONEDA"


class TripType(str, PyEnum):
    IDA = "IDA"
    VUELTA = "VUELTA"


class PlanType(str, PyEnum):
    VIAJES_10 = "VIAJES_10"
    VIAJES_20 = "VIAJES_20"
    VIAJES_30 = "VIAJES_30"
    VIAJES_40 = "VIAJES_40"


class PaymentStatus(str, PyEnum):
    PAGADO = "PAGADO"
    PENDIENTE = "PENDIENTE"
    VENCIDO = "VENCIDO"


class ReservationStatus(str, PyEnum):
    CONFIRMADO = "CONFIRMADO"
    LISTA_ESPERA = "LISTA_ESPERA"
    CANCELADO = "CANCELADO"


class CheckinResult(str, PyEnum):
    OK = "OK"
    REJECTED = "REJECTED"


class TokenStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    pickup_point_default: Mapped[PickupPoint] = mapped_column(SAEnum(PickupPoint, name="pickup_point_enum"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="passenger")
    daily_passes: Mapped[list["DailyPass"]] = relationship(back_populates="passenger")
    tokens: Mapped[list["QrToken"]] = relationship(back_populates="passenger")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    email_verified_at = Column(DateTime, nullable=True)
    phone_verified_at = Column(DateTime, nullable=True)
    app_enabled = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime, nullable=True)
    accepted_terms_version = Column(String, nullable=True)
    accepted_terms_at = Column(DateTime, nullable=True)


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid_col(),
        ForeignKey("passengers.id"),
        nullable=True,
        index=True,
    )

    identifier: Mapped[str] = mapped_column(String(200), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    passenger: Mapped["Passenger | None"] = relationship()

class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(
        _uuid_col(),
        ForeignKey("passengers.id"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    passenger: Mapped["Passenger"] = relationship()

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("passenger_id", "month", name="uq_subscription_passenger_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    month: Mapped[date] = mapped_column(Date)

    plan_type: Mapped[PlanType] = mapped_column(SAEnum(PlanType, name="plan_type_enum"))
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status_enum"),
        default=PaymentStatus.PENDIENTE,
    )

    rides_included: Mapped[int] = mapped_column(Integer, default=20)
    rides_used_ida: Mapped[int] = mapped_column(Integer, default=0)
    rides_used_vuelta: Mapped[int] = mapped_column(Integer, default=0)

    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    passenger: Mapped[Passenger] = relationship(back_populates="subscriptions")
    
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DailyPass(Base):
    __tablename__ = "daily_passes"
    __table_args__ = (
        UniqueConstraint("passenger_id", "service_date", "trip_type", name="uq_daily_pass"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)

    trip_type: Mapped[TripType] = mapped_column(SAEnum(TripType, name="trip_type_enum"))
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status_enum"),
        default=PaymentStatus.PENDIENTE,
    )
    reservation_status: Mapped[ReservationStatus] = mapped_column(
        SAEnum(ReservationStatus, name="reservation_status_enum"),
        default=ReservationStatus.LISTA_ESPERA,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    passenger: Mapped[Passenger] = relationship(back_populates="daily_passes")

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    service_date: Mapped[date] = mapped_column(Date, index=True)
    trip_type: Mapped[TripType] = mapped_column(SAEnum(TripType, name="trip_type_enum"), index=True)
    pickup_point: Mapped[PickupPoint] = mapped_column(SAEnum(PickupPoint, name="pickup_point_enum"))

    passenger_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid_col(),
        ForeignKey("passengers.id"),
        nullable=True,
        index=True,
    )

    result: Mapped[CheckinResult] = mapped_column(SAEnum(CheckinResult, name="checkin_result_enum"))
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    entitlement: Mapped[str | None] = mapped_column(String(20), nullable=True)

    scanner_user: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_meta: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_checkins_service_trip", Checkin.service_date, Checkin.trip_type)
Index("ix_checkins_passenger_date", Checkin.passenger_id, Checkin.service_date)


class QrToken(Base):
    __tablename__ = "qr_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[TokenStatus] = mapped_column(
        SAEnum(TokenStatus, name="token_status_enum"),
        default=TokenStatus.ACTIVE,
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    valid_to: Mapped[datetime] = mapped_column(DateTime, index=True)

    passenger: Mapped[Passenger] = relationship(back_populates="tokens")

class OneTimeTokenStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    REVOKED = "REVOKED"


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    daily_pass_id: Mapped[int] = mapped_column(Integer, ForeignKey("daily_passes.id"), index=True)

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    service_date: Mapped[date] = mapped_column(Date, index=True)
    trip_type: Mapped[TripType] = mapped_column(SAEnum(TripType, name="trip_type_enum"), index=True)

    status: Mapped[OneTimeTokenStatus] = mapped_column(
        SAEnum(OneTimeTokenStatus, name="one_time_token_status_enum"),
        default=OneTimeTokenStatus.ACTIVE,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

@router.post("/monthly-plan/checkout", dependencies=[Depends(security)])
def create_monthly_plan_checkout(
    payload: MonthlyPlanCheckoutIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    import os

    token = credentials.credentials

    if payload.plan_type not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="PlanType inválido")

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        buy_order = f"plan-{uuid.uuid4().hex[:26]}"
        session_id = str(passenger.id)
        amount = PLAN_PRICES[payload.plan_type]

        return_url = f"{os.getenv('APP_BASE_URL')}/app/payments/webpay/return"

        tx = Transaction(get_webpay_options())
        response = tx.create(buy_order, session_id, amount, return_url)

        # aquí debes guardar tu payment_intent en BD
        # kind=MONTHLY_PLAN, buy_order=buy_order, payload_json={month, plan_type}, status=PENDING

        return {
            "ok": True,
            "payment_url": response["url"],
            "token": response["token"],
        }
@router.post("/daily-pass/checkout", dependencies=[Depends(security)])
def create_daily_pass_checkout(
    payload: DailyPassCheckoutIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    import os

    token = credentials.credentials

    if payload.trip_type not in ["IDA", "VUELTA"]:
        raise HTTPException(status_code=400, detail="trip_type inválido")

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        buy_order = f"daily-{uuid.uuid4().hex[:26]}"
        session_id = str(passenger.id)
        amount = DAILY_PASS_PRICE

        return_url = f"{os.getenv('APP_BASE_URL')}/app/payments/webpay/return"

        tx = Transaction(get_webpay_options())
        response = tx.create(buy_order, session_id, amount, return_url)

        # aquí debes guardar tu payment_intent en BD
        # kind=DAILY_PASS, buy_order=buy_order, payload_json={service_date, trip_type}, status=PENDING

        return {
            "ok": True,
            "payment_url": response["url"],
            "token": response["token"],
        }
@router.post("/webpay/return")
def webpay_return(token_ws: str):
    import os

    with get_db() as db:
        tx = Transaction(get_webpay_options())
        result = tx.commit(token_ws)

        buy_order = result.get("buy_order")
        status = result.get("status")
        response_code = result.get("response_code", -1)

        # busca payment_intent por buy_order
        # intent = ...

        if status == "AUTHORIZED" and response_code == 0:
            # marca intent como PAID
            # payload = json.loads(intent.payload_json)

            # si intent.kind == "MONTHLY_PLAN":
            #   reutiliza tu lógica de activate_subscription
            # si intent.kind == "DAILY_PASS":
            #   reutiliza tu lógica de create_daily_pass

            return RedirectResponse(
                url=f"{os.getenv('FRONTEND_BASE_URL')}/payments?payment=success"
            )

        # si falla
        return RedirectResponse(
            url=f"{os.getenv('FRONTEND_BASE_URL')}/payments?payment=failed"
        )

