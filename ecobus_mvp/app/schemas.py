from __future__ import annotations

from datetime import date
from pydantic import BaseModel, EmailStr, Field
from pydantic import BaseModel, EmailStr
from typing import Optional

from .models import PickupPoint, PlanType, PaymentStatus, TripType, ReservationStatus


class PassengerCreate(BaseModel):
    full_name: str
    phone: str
    email: EmailStr | None = None
    pickup_point_default: PickupPoint
    is_active: bool = True


class PassengerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    pickup_point_default: PickupPoint | None = None
    is_active: bool | None = None


class PassengerOut(BaseModel):
    id: str
    code: str
    full_name: str
    phone: str
    email: str | None
    pickup_point_default: PickupPoint
    is_active: bool


class ActivateSubscriptionIn(BaseModel):
    passenger_code: str
    month: date = Field(description="First day of the month, e.g. 2026-03-01")
    plan_type: PlanType
    payment_status: PaymentStatus = PaymentStatus.PAGADO
    notes: str | None = None


class DailyPassCreate(BaseModel):
    passenger_code: str
    service_date: date
    trip_type: TripType
    payment_status: PaymentStatus = PaymentStatus.PENDIENTE
    reservation_status: ReservationStatus = ReservationStatus.LISTA_ESPERA


class DailyPassUpdate(BaseModel):
    payment_status: PaymentStatus | None = None
    reservation_status: ReservationStatus | None = None


class ValidateResponse(BaseModel):
    result: str
    full_name: str | None = None
    code: str | None = None
    reason: str | None = None
    message: str
    plan: str | None = None
    month: date | None = None
    pickup_point: str | None = None
    rides_included: int | None = None
    rides_used_total: int | None = None
    rides_remaining: int | None = None

class OtpRequestIn(BaseModel):
    identifier: str  # email o telefono


class OtpRequestOut(BaseModel):
    ok: bool
    channel: str
    masked_destination: str
    expires_in_seconds: int


class OtpVerifyIn(BaseModel):
    identifier: str
    code: str


class AuthMeOut(BaseModel):
    ok: bool
    passenger_id: int
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    app_enabled: bool


class OtpVerifyOut(BaseModel):
    ok: bool
    access_token: str
    expires_in_seconds: int
    passenger: AuthMeOut
