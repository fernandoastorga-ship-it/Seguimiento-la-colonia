from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field

from .models import (
    PickupPoint,
    PlanType,
    PaymentStatus,
    TripType,
    ReservationStatus,
    ServiceCode,
)


class PassengerCreate(BaseModel):
    full_name: str
    phone: str
    email: EmailStr | None = None
    pickup_point_default: PickupPoint
    service_code: ServiceCode
    is_active: bool = True


class PassengerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    pickup_point_default: PickupPoint | None = None
    service_code: ServiceCode | None = None
    is_active: bool | None = None


class PassengerOut(BaseModel):
    id: str
    code: str
    full_name: str
    phone: str
    email: str | None
    pickup_point_default: PickupPoint
    service_code: ServiceCode
    service_name: str
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
    service_code: str | None = None
    service_name: str | None = None
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
    passenger_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    app_enabled: bool


class OtpVerifyOut(BaseModel):
    ok: bool
    access_token: str
    expires_in_seconds: int
    passenger: AuthMeOut

class TransferNotifyIn(BaseModel):
    request_type: Literal["MONTHLY", "DAILY"]
    payload: dict
    notes: str | None = None


class TransferRequestOut(BaseModel):
    id: int
    passenger_id: str
    request_type: str
    status: str
    payload: dict
    notes: str | None = None
    admin_notes: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class TransferReviewIn(BaseModel):
    admin_notes: str | None = None
    reviewed_by: str | None = None

class AppDashboardPassengerOut(BaseModel):
    id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    pickup_point: str | None = None
    pickup_default: str | None = None
    code: str | None = None
    app_enabled: bool
    email_verified_at: datetime | None = None
    phone_verified_at: datetime | None = None
    last_login_at: datetime | None = None


class AppDashboardSubscriptionOut(BaseModel):
    has_plan: bool
    status: str
    plan_type: str | None = None
    payment_status: str | None = None
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    rides_included: int = 0
    rides_used: int = 0
    rides_used_total: int = 0
    rides_remaining: int = 0
    days_left: int | None = None


class AppDashboardDailyPassOut(BaseModel):
    id: int
    service_date: date
    trip_type: str
    payment_status: str
    reservation_status: str


class AppDashboardOut(BaseModel):
    passenger: AppDashboardPassengerOut
    subscription: AppDashboardSubscriptionOut
    daily_pass: AppDashboardDailyPassOut | None = None

