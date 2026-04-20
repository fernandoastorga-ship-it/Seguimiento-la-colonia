from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, desc, select
from pydantic import BaseModel

from app.db import get_db
from app.models import (
    DailyPass,
    Subscription,
    PlanType,
    PaymentStatus,
    ReservationStatus,
)
from app.utils import now_local
from app.services.auth_service import get_passenger_from_token

router = APIRouter(prefix="/app/payments", tags=["App Payments"])

security = HTTPBearer()


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _get_current_subscription(db, passenger_id, today: date):
    now_dt = now_local().replace(tzinfo=None)

    stmt = (
        select(Subscription)
        .where(
            and_(
                Subscription.passenger_id == passenger_id,
                Subscription.is_deleted == False,
                Subscription.payment_status == PaymentStatus.PAGADO,
                Subscription.activated_at != None,
                Subscription.expires_at != None,
                Subscription.activated_at <= now_dt,
                Subscription.expires_at >= now_dt,
            )
        )
        .order_by(desc(Subscription.activated_at), desc(Subscription.id))
    )
    return db.execute(stmt).scalars().first()


def _get_today_daily_pass(db, passenger_id, today: date):
    stmt = (
        select(DailyPass)
        .where(
            and_(
                DailyPass.passenger_id == passenger_id,
                DailyPass.service_date == today,
                DailyPass.is_deleted == False,
            )
        )
        .order_by(desc(DailyPass.id))
    )
    return db.execute(stmt).scalars().first()


@router.get("/health")
def payments_health():
    return {
        "ok": True,
        "module": "app_payments",
        "message": "Módulo de pagos operativo",
    }


@router.get("/", dependencies=[Depends(security)])
def get_payment_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    today = date.today()

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        subscription = _get_current_subscription(db, passenger.id, today)
        daily_pass = _get_today_daily_pass(db, passenger.id, today)

        monthly_plan_data = {
            "has_monthly_plan": False,
            "month": _month_start(today),
            "plan_type": None,
            "payment_status": None,
            "activated_at": None,
            "expires_at": None,
            "rides_included": 0,
            "rides_used": 0,
            "rides_remaining": 0,
            "is_paid": False,
        }

        if subscription:
            rides_used = (subscription.rides_used_ida or 0) + (subscription.rides_used_vuelta or 0)
            rides_included = subscription.rides_included or 0
            rides_remaining = max(rides_included - rides_used, 0)

            monthly_plan_data = {
                "has_monthly_plan": True,
                "month": subscription.month,
                "plan_type": subscription.plan_type.value,
                "payment_status": subscription.payment_status.value,
                "activated_at": subscription.activated_at,
                "expires_at": subscription.expires_at,
                "rides_included": rides_included,
                "rides_used": rides_used,
                "rides_remaining": rides_remaining,
                "is_paid": subscription.payment_status.value == "PAGADO",
            }

        daily_pass_data = {
            "has_daily_pass_today": False,
            "id": None,
            "service_date": None,
            "trip_type": None,
            "payment_status": None,
            "reservation_status": None,
            "is_paid": False,
            "is_confirmed": False,
        }

        if daily_pass:
            payment_status = daily_pass.payment_status.value
            reservation_status = daily_pass.reservation_status.value

            daily_pass_data = {
                "has_daily_pass_today": True,
                "id": daily_pass.id,
                "service_date": daily_pass.service_date,
                "trip_type": daily_pass.trip_type.value,
                "payment_status": payment_status,
                "reservation_status": reservation_status,
                "is_paid": payment_status == "PAGADO",
                "is_confirmed": reservation_status == "CONFIRMADO",
            }

        return {
            "passenger": {
                "id": str(passenger.id),
                "full_name": passenger.full_name,
            },
            "monthly_plan": monthly_plan_data,
            "daily_pass_today": daily_pass_data,
            "summary": {
                "has_any_active_payment_context": monthly_plan_data["has_monthly_plan"] or daily_pass_data["has_daily_pass_today"],
                "monthly_plan_paid": monthly_plan_data["is_paid"],
                "daily_pass_paid": daily_pass_data["is_paid"],
                "daily_pass_confirmed": daily_pass_data["is_confirmed"],
            },
        }

        
class MonthlyPlanPurchaseIn(BaseModel):
    month: date
    plan_type: str


class DailyPassPurchaseIn(BaseModel):
    service_date: date
    trip_type: str


@router.post("/monthly-plan/purchase", dependencies=[Depends(security)])
def purchase_monthly_plan(
    payload: MonthlyPlanPurchaseIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    PLAN_RIDES = {
        "VIAJES_10": 10,
        "VIAJES_20": 20,
        "VIAJES_30": 30,
        "VIAJES_40": 40,
    }

    if payload.plan_type not in PLAN_RIDES:
        raise HTTPException(
            status_code=400,
            detail="PlanType inválido. Usa VIAJES_10, VIAJES_20, VIAJES_30 o VIAJES_40.",
        )

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        rides_included = PLAN_RIDES[payload.plan_type]

        sub = db.execute(
            select(Subscription).where(
                and_(
                    Subscription.passenger_id == passenger.id,
                    Subscription.month == payload.month,
                    Subscription.is_deleted == False,
                )
            )
        ).scalar_one_or_none()

        now_dt = now_local().replace(tzinfo=None)
        expires_dt = now_dt + timedelta(days=30)

        if not sub:
            sub = Subscription(
                passenger_id=passenger.id,
                month=payload.month,
                plan_type=PlanType[payload.plan_type],
                payment_status=PaymentStatus.PAGADO,
                rides_included=rides_included,
                rides_used_ida=0,
                rides_used_vuelta=0,
                activated_at=now_dt,
                expires_at=expires_dt,
                notes="Compra desde app",
            )
        else:
            sub.plan_type = PlanType[payload.plan_type]
            sub.payment_status = PaymentStatus.PAGADO
            sub.rides_included = rides_included
            sub.activated_at = now_dt
            sub.expires_at = expires_dt
            sub.notes = "Compra/renovación desde app"

        db.add(sub)
        db.flush()



        return {
            "ok": True,
            "message": "Plan mensual activado correctamente.",
            "passenger": {
                "id": str(passenger.id),
                "full_name": passenger.full_name,
                "code": passenger.code,
            },
            "monthly_plan": {
                "month": payload.month,
                "plan_type": payload.plan_type,
                "payment_status": "PAGADO",
                "rides_included": rides_included,
            },
        }
