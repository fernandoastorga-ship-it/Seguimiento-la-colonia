from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models import Passenger, Subscription, DailyPass, PaymentStatus


# -------------------------
# Helpers de fecha
# -------------------------

def _month_start(d: date) -> date:
    return d.replace(day=1)


# -------------------------
# Queries base
# -------------------------

def _get_passenger(db: Session, passenger_id):
    return (
        db.query(Passenger)
        .filter(
            Passenger.id == passenger_id,
            Passenger.is_deleted == False,
        )
        .first()
    )


def _get_current_subscription(db: Session, passenger_id, today: date):
    ms = _month_start(today)

    return (
        db.query(Subscription)
        .filter(
            Subscription.passenger_id == passenger_id,
            Subscription.month == ms,
            Subscription.is_deleted == False,
        )
        .order_by(desc(Subscription.activated_at), desc(Subscription.id))
        .first()
    )


def _get_today_daily_pass(db: Session, passenger_id, today: date):
    return (
        db.query(DailyPass)
        .filter(
            DailyPass.passenger_id == passenger_id,
            DailyPass.service_date == today,
            DailyPass.is_deleted == False,
        )
        .order_by(desc(DailyPass.id))
        .first()
    )


# -------------------------
# Lógica de negocio
# -------------------------

def _compute_subscription_summary(sub: Subscription | None):
    if not sub:
        return {
            "has_plan": False,
            "status": "no_plan",
            "plan_type": None,
            "payment_status": None,
            "activated_at": None,
            "rides_included": 0,
            "rides_used": 0,
            "rides_remaining": 0,
        }

    rides_used = (sub.rides_used_ida or 0) + (sub.rides_used_vuelta or 0)
    rides_included = sub.rides_included or 0
    rides_remaining = max(rides_included - rides_used, 0)

    payment_status = sub.payment_status.value

    # Estado del plan
    if sub.payment_status == PaymentStatus.PENDIENTE:
        status = "pending_payment"
    elif not sub.activated_at:
        status = "inactive"
    elif rides_remaining <= 0:
        status = "exhausted"
    else:
        status = "active"

    return {
        "has_plan": True,
        "status": status,
        "plan_type": sub.plan_type.value,
        "payment_status": payment_status,
        "activated_at": sub.activated_at,
        "rides_included": rides_included,
        "rides_used": rides_used,
        "rides_remaining": rides_remaining,
    }


# -------------------------
# MAIN SERVICE
# -------------------------

def build_app_dashboard(db: Session, passenger_id, today: date):
    passenger = _get_passenger(db, passenger_id)

    if not passenger:
        return None

    subscription = _get_current_subscription(db, passenger.id, today)
    daily_pass = _get_today_daily_pass(db, passenger.id, today)

    sub_summary = _compute_subscription_summary(subscription)

    daily_pass_data = None
    if daily_pass:
        daily_pass_data = {
            "id": daily_pass.id,
            "service_date": daily_pass.service_date,
            "trip_type": daily_pass.trip_type.value,
            "payment_status": daily_pass.payment_status.value,
            "reservation_status": daily_pass.reservation_status.value,
        }

    return {
        "passenger": {
            "id": str(passenger.id),
            "full_name": passenger.full_name,
            "email": passenger.email,
            "phone": passenger.phone,
            "pickup_point": passenger.pickup_point_default.value if passenger.pickup_point_default else None,
            "app_enabled": passenger.app_enabled,
            "email_verified_at": passenger.email_verified_at,
            "phone_verified_at": passenger.phone_verified_at,
            "last_login_at": passenger.last_login_at,
        },
        "subscription": sub_summary,
        "daily_pass": daily_pass_data,
    }
