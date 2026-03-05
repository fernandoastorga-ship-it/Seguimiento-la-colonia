from __future__ import annotations

import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid_col():
    # Works for Postgres and falls back to string for SQLite.
    try:
        return PG_UUID(as_uuid=True)
    except Exception:
        return String(36)


class Base(DeclarativeBase):
    pass


class PickupPoint(str, enum.Enum):
    LA_COLONIA = "LA_COLONIA"
    CRUCE_MALLOCO = "CRUCE_MALLOCO"


class TripType(str, enum.Enum):
    IDA = "IDA"
    VUELTA = "VUELTA"


class PlanType(str, enum.Enum):
    IDA = "IDA"
    VUELTA = "VUELTA"
    IDA_VUELTA = "IDA_VUELTA"


class PaymentStatus(str, enum.Enum):
    PAGADO = "PAGADO"
    PENDIENTE = "PENDIENTE"
    VENCIDO = "VENCIDO"


class ReservationStatus(str, enum.Enum):
    CONFIRMADO = "CONFIRMADO"
    LISTA_ESPERA = "LISTA_ESPERA"
    CANCELADO = "CANCELADO"


class CheckinResult(str, enum.Enum):
    OK = "OK"
    REJECTED = "REJECTED"


class TokenStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    pickup_point_default: Mapped[PickupPoint] = mapped_column(Enum(PickupPoint))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="passenger")
    daily_passes: Mapped[list["DailyPass"]] = relationship(back_populates="passenger")
    tokens: Mapped[list["QrToken"]] = relationship(back_populates="passenger")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("passenger_id", "month", name="uq_subscription_passenger_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    month: Mapped[date] = mapped_column(Date)  # first day of month
    plan_type: Mapped[PlanType] = mapped_column(Enum(PlanType))
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDIENTE)

    rides_included: Mapped[int] = mapped_column(Integer, default=20)
    rides_used_ida: Mapped[int] = mapped_column(Integer, default=0)
    rides_used_vuelta: Mapped[int] = mapped_column(Integer, default=0)

    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    passenger: Mapped[Passenger] = relationship(back_populates="subscriptions")


class DailyPass(Base):
    __tablename__ = "daily_passes"
    __table_args__ = (
        UniqueConstraint("passenger_id", "service_date", "trip_type", name="uq_daily_pass"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    trip_type: Mapped[TripType] = mapped_column(Enum(TripType))
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDIENTE)
    reservation_status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus),
        default=ReservationStatus.LISTA_ESPERA,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    passenger: Mapped[Passenger] = relationship(back_populates="daily_passes")


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    service_date: Mapped[date] = mapped_column(Date, index=True)
    trip_type: Mapped[TripType] = mapped_column(Enum(TripType), index=True)
    pickup_point: Mapped[PickupPoint] = mapped_column(Enum(PickupPoint))

    passenger_id: Mapped[uuid.UUID | None] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), nullable=True, index=True)

    result: Mapped[CheckinResult] = mapped_column(Enum(CheckinResult))
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    scanner_user: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_meta: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_checkins_service_trip", Checkin.service_date, Checkin.trip_type)
Index("ix_checkins_passenger_date", Checkin.passenger_id, Checkin.service_date)


class QrToken(Base):
    __tablename__ = "qr_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[uuid.UUID] = mapped_column(_uuid_col(), ForeignKey("passengers.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[TokenStatus] = mapped_column(Enum(TokenStatus), default=TokenStatus.ACTIVE)
    valid_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    valid_to: Mapped[datetime] = mapped_column(DateTime, index=True)

    passenger: Mapped[Passenger] = relationship(back_populates="tokens")
