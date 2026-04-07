from __future__ import annotations
import json
import uuid
from datetime import datetime, date, timedelta
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
    JSON,
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

class ServiceCode(str, PyEnum):
    LA_COLONIA = "LA_COLONIA"
    ALTUE = "ALTUE"

class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[ServiceCode] = mapped_column(
        SAEnum(ServiceCode, name="service_code_enum"),
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    passengers: Mapped[list["Passenger"]] = relationship(back_populates="service")

class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    pickup_point_default: Mapped[PickupPoint] = mapped_column(SAEnum(PickupPoint, name="pickup_point_enum"))

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    service: Mapped["Service"] = relationship(back_populates="passengers")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="passenger")
    daily_passes: Mapped[list["DailyPass"]] = relationship(back_populates="passenger")
    tokens: Mapped[list["QrToken"]] = relationship(back_populates="passenger")
    checkins: Mapped[list["Checkin"]] = relationship(back_populates="passenger")

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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
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

class TransferRequestStatus(str, PyEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TransferRequestType(str, PyEnum):
    MONTHLY = "MONTHLY"
    DAILY = "DAILY"


class TransferRequest(Base):
    __tablename__ = "transfer_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    passenger_id: Mapped[uuid.UUID] = mapped_column(
        _uuid_col(),
        ForeignKey("passengers.id"),
        index=True,
        nullable=False,
    )

    request_type: Mapped[TransferRequestType] = mapped_column(
        SAEnum(TransferRequestType, name="transfer_request_type_enum"),
        nullable=False,
    )

    status: Mapped[TransferRequestStatus] = mapped_column(
        SAEnum(TransferRequestStatus, name="transfer_request_status_enum"),
        default=TransferRequestStatus.PENDING,
        nullable=False,
        index=True,
    )

    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    passenger = relationship("Passenger")

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

    # 🔽 AGREGA ESTO (clave del fix)
    passenger: Mapped["Passenger | None"] = relationship(back_populates="checkins")
    # 🔼

    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id"),
        nullable=True,
        index=True
    )
    service: Mapped["Service | None"] = relationship()

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

class PaymentIntentKind(str, PyEnum):
    MONTHLY_PLAN = "MONTHLY_PLAN"
    DAILY_PASS = "DAILY_PASS"


class PaymentIntentStatus(str, PyEnum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    passenger_id: Mapped[uuid.UUID] = mapped_column(
        _uuid_col(),
        ForeignKey("passengers.id"),
        index=True,
        nullable=False,
    )

    kind: Mapped[PaymentIntentKind] = mapped_column(
        SAEnum(PaymentIntentKind, name="payment_intent_kind_enum"),
        index=True,
        nullable=False,
    )

    status: Mapped[PaymentIntentStatus] = mapped_column(
        SAEnum(PaymentIntentStatus, name="payment_intent_status_enum"),
        index=True,
        nullable=False,
        default=PaymentIntentStatus.PENDING,
    )

    buy_order: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    webpay_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    webpay_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    authorization_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    passenger: Mapped["Passenger"] = relationship()

