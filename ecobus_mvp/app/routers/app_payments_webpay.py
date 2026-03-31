from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.db import get_db
from app.models import (
    Passenger,
    Subscription,
    DailyPass,
    PaymentIntent,
    PaymentIntentKind,
    PaymentIntentStatus,
    PlanType,
    PaymentStatus,
    ReservationStatus,
    TripType,
)
from app.services.webpay_rest import (
    webpay_create_transaction,
    webpay_commit_transaction,
)

# IMPORTANTE:
# usa aquí los mismos imports reales que ya tienes funcionando en tu app
# para seguridad y resolución de pasajero autenticado.
from app.auth_helpers import security, get_passenger_from_token


router = APIRouter(prefix="/app/payments/webpay", tags=["app-payments-webpay"])


# ----------------------------
# CONFIG PRECIOS
# ----------------------------
PLAN_PRICES = {
    "VIAJES_10": 19000,
    "VIAJES_20": 35000,
    "VIAJES_30": 49000,
    "VIAJES_40": 60000,
}

DAILY_PASS_PRICE = 2000  # AJUSTA ESTE VALOR AL REAL DE TU NEGOCIO


# ----------------------------
# SCHEMAS
# ----------------------------
class MonthlyPlanCheckoutIn(BaseModel):
    month: date
    plan_type: str
    use_webpay_fee: bool = False


class DailyPassCheckoutIn(BaseModel):
    service_date: date
    trip_type: str
    use_webpay_fee: bool = False


# ----------------------------
# HELPERS
# ----------------------------
def _build_return_url() -> str:
    import os
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("Falta APP_BASE_URL en variables de entorno.")
    return f"{base}/app/payments/webpay/return"


def _build_frontend_payments_url(status: str, kind: str = "", extra: str = "") -> str:
    import os
    frontend = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
    if not frontend:
        raise RuntimeError("Falta FRONTEND_BASE_URL en variables de entorno.")

    url = f"{frontend}/payments?payment={status}"
    if kind:
        url += f"&kind={kind}"
    if extra:
        url += extra
    return url


def _monthly_rides_for_plan(plan_type: str) -> int:
    mapping = {
        "VIAJES_10": 10,
        "VIAJES_20": 20,
        "VIAJES_30": 30,
        "VIAJES_40": 40,
    }
    if plan_type not in mapping:
        raise HTTPException(status_code=400, detail="PlanType inválido")
    return mapping[plan_type]


def _normalize_month_first_day(value: date) -> date:
    return date(value.year, value.month, 1)


def _safe_buy_order(prefix: str) -> str:
    # buy_order máximo 26 caracteres según Webpay
    suffix = uuid.uuid4().hex[:20]
    raw = f"{prefix}{suffix}"
    return raw[:26]


def _safe_session_id(passenger_id: str) -> str:
    # session_id máximo 61 caracteres según Webpay
    return passenger_id[:61]


def _upsert_monthly_subscription(
    db,
    passenger: Passenger,
    month: date,
    plan_type: str,
):
    month_norm = _normalize_month_first_day(month)

    existing = (
        db.query(Subscription)
        .filter(
            Subscription.passenger_id == passenger.id,
            Subscription.month == month_norm,
            Subscription.is_deleted == False,
        )
        .first()
    )

    rides_included = _monthly_rides_for_plan(plan_type)

    if existing:
        existing.plan_type = PlanType(plan_type)
        existing.payment_status = PaymentStatus.PAGADO
        existing.rides_included = rides_included
        existing.activated_at = datetime.utcnow()
        existing.notes = "Pago Webpay aprobado"
        db.flush()
        return existing

    sub = Subscription(
        passenger_id=passenger.id,
        month=month_norm,
        plan_type=PlanType(plan_type),
        payment_status=PaymentStatus.PAGADO,
        rides_included=rides_included,
        rides_used_ida=0,
        rides_used_vuelta=0,
        activated_at=datetime.utcnow(),
        notes="Pago Webpay aprobado",
    )
    db.add(sub)
    db.flush()
    return sub


def _create_daily_pass_paid(
    db,
    passenger: Passenger,
    service_date: date,
    trip_type: str,
):
    existing = (
        db.query(DailyPass)
        .filter(
            DailyPass.passenger_id == passenger.id,
            DailyPass.service_date == service_date,
            DailyPass.trip_type == TripType(trip_type),
            DailyPass.is_deleted == False,
        )
        .first()
    )

    if existing:
        existing.payment_status = PaymentStatus.PAGADO
        existing.reservation_status = ReservationStatus.CONFIRMADO
        db.flush()
        return existing

    dp = DailyPass(
        passenger_id=passenger.id,
        service_date=service_date,
        trip_type=TripType(trip_type),
        payment_status=PaymentStatus.PAGADO,
        reservation_status=ReservationStatus.CONFIRMADO,
    )
    db.add(dp)
    db.flush()
    return dp


# ----------------------------
# INIT MONTHLY PLAN
# ----------------------------
@router.post("/monthly-plan/init", dependencies=[Depends(security)])
def init_monthly_plan_payment(
    payload: MonthlyPlanCheckoutIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    if payload.plan_type not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="PlanType inválido")

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        buy_order = _safe_buy_order("mp")
        session_id = _safe_session_id(str(passenger.id))
        amount = PLAN_PRICES[payload.plan_type]
        
        if payload.use_webpay_fee:
            amount = int(round(amount * 1.05))

        webpay_resp = webpay_create_transaction(
            buy_order=buy_order,
            session_id=session_id,
            amount=amount,
            return_url=_build_return_url(),
        )

        intent = PaymentIntent(
            passenger_id=passenger.id,
            kind=PaymentIntentKind.MONTHLY_PLAN,
            status=PaymentIntentStatus.PENDING,
            buy_order=buy_order,
            session_id=session_id,
            amount=amount,
            payload_json=json.dumps(
                {
                    "month": payload.month.isoformat(),
                    "plan_type": payload.plan_type,
                    "use_webpay_fee": payload.use_webpay_fee,
                }
            ),
            webpay_token=webpay_resp.get("token"),
            webpay_response_json=json.dumps(webpay_resp),
        )
        db.add(intent)
        db.commit()

        return {
            "ok": True,
            "kind": "MONTHLY_PLAN",
            "buy_order": buy_order,
            "payment_url": webpay_resp["url"],
            "token": webpay_resp["token"],
        }


# ----------------------------
# INIT DAILY PASS
# ----------------------------
@router.post("/daily-pass/init", dependencies=[Depends(security)])
def init_daily_pass_payment(
    payload: DailyPassCheckoutIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    if payload.trip_type not in ["IDA", "VUELTA"]:
        raise HTTPException(status_code=400, detail="trip_type inválido")

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        buy_order = _safe_buy_order("dp")
        session_id = _safe_session_id(str(passenger.id))
        amount = DAILY_PASS_PRICE

        if payload.use_webpay_fee:
            amount = int(round(amount * 1.05))

        webpay_resp = webpay_create_transaction(
            buy_order=buy_order,
            session_id=session_id,
            amount=amount,
            return_url=_build_return_url(),
        )

        intent = PaymentIntent(
            passenger_id=passenger.id,
            kind=PaymentIntentKind.DAILY_PASS,
            status=PaymentIntentStatus.PENDING,
            buy_order=buy_order,
            session_id=session_id,
            amount=amount,
            payload_json=json.dumps(
                {
                    "service_date": payload.service_date.isoformat(),
                    "trip_type": payload.trip_type,
                    "use_webpay_fee": payload.use_webpay_fee,
                }
            ),
            webpay_token=webpay_resp.get("token"),
            webpay_response_json=json.dumps(webpay_resp),
        )
        db.add(intent)
        db.commit()

        return {
            "ok": True,
            "kind": "DAILY_PASS",
            "buy_order": buy_order,
            "payment_url": webpay_resp["url"],
            "token": webpay_resp["token"],
        }


# ----------------------------
# RETURN / COMMIT
# ----------------------------
@router.post("/return")
def webpay_return_post(
    token_ws: Optional[str] = Form(default=None),
    TBK_TOKEN: Optional[str] = Form(default=None),
):
    return _handle_webpay_return(token_ws=token_ws, tbk_token=TBK_TOKEN)


@router.get("/return")
def webpay_return_get(
    token_ws: Optional[str] = None,
    TBK_TOKEN: Optional[str] = None,
):
    return _handle_webpay_return(token_ws=token_ws, tbk_token=TBK_TOKEN)


def _handle_webpay_return(token_ws: Optional[str], tbk_token: Optional[str]):
    # Webpay abortado/cancelado por el usuario
    if tbk_token:
        return RedirectResponse(
            url=_build_frontend_payments_url("aborted"),
            status_code=303,
        )

    if not token_ws:
        return RedirectResponse(
            url=_build_frontend_payments_url("failed"),
            status_code=303,
        )

    with get_db() as db:
        intent = (
            db.query(PaymentIntent)
            .filter(PaymentIntent.webpay_token == token_ws)
            .first()
        )

        if not intent:
            return RedirectResponse(
                url=_build_frontend_payments_url("failed"),
                status_code=303,
            )

        try:
            result = webpay_commit_transaction(token_ws)
        except Exception:
            intent.status = PaymentIntentStatus.FAILED
            intent.webpay_response_json = json.dumps(
                {"commit_error": True, "token_ws": token_ws}
            )
            db.commit()

            return RedirectResponse(
                url=_build_frontend_payments_url("failed"),
                status_code=303,
            )

        intent.webpay_response_json = json.dumps(result)

        status = result.get("status")
        response_code = result.get("response_code", -1)

        if status == "AUTHORIZED" and response_code == 0:
            passenger = (
                db.query(Passenger)
                .filter(Passenger.id == intent.passenger_id)
                .first()
            )

            if not passenger:
                intent.status = PaymentIntentStatus.FAILED
                db.commit()
                return RedirectResponse(
                    url=_build_frontend_payments_url("failed"),
                    status_code=303,
                )

            payload = json.loads(intent.payload_json)

            if intent.kind == PaymentIntentKind.MONTHLY_PLAN:
                _upsert_monthly_subscription(
                    db=db,
                    passenger=passenger,
                    month=date.fromisoformat(payload["month"]),
                    plan_type=payload["plan_type"],
                )
                kind = "monthly_plan"

            elif intent.kind == PaymentIntentKind.DAILY_PASS:
                _create_daily_pass_paid(
                    db=db,
                    passenger=passenger,
                    service_date=date.fromisoformat(payload["service_date"]),
                    trip_type=payload["trip_type"],
                )
                kind = "daily_pass"

            else:
                intent.status = PaymentIntentStatus.FAILED
                db.commit()
                return RedirectResponse(
                    url=_build_frontend_payments_url("failed"),
                    status_code=303,
                )

            intent.status = PaymentIntentStatus.AUTHORIZED
            intent.authorization_code = result.get("authorization_code")
            tx_date = result.get("transaction_date")
            if tx_date:
                try:
                    intent.transaction_date = datetime.fromisoformat(tx_date.replace("Z", "+00:00"))
                except Exception:
                    intent.transaction_date = None
            intent.committed_at = datetime.utcnow()

            db.commit()

            return RedirectResponse(
                url=_build_frontend_payments_url("success", kind=kind),
                status_code=303,
            )

        intent.status = PaymentIntentStatus.FAILED
        db.commit()

        return RedirectResponse(
            url=_build_frontend_payments_url("failed"),
            status_code=303,
        )
