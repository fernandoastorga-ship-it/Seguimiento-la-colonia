from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, and_, func, desc

from .config import settings
from .db import ENGINE, get_db
from .models import (
    Base,
    Passenger,
    Subscription,
    DailyPass,
    Checkin,
    QrToken,
    TripType,
    PickupPoint,
    PaymentStatus,
    PlanType,
    ReservationStatus,
    CheckinResult,
    TokenStatus,
    OneTimeToken,
    OneTimeTokenStatus,
)
from .schemas import (
    PassengerCreate,
    PassengerUpdate,
    PassengerOut,
    ActivateSubscriptionIn,
    DailyPassCreate,
    DailyPassUpdate,
    ValidateResponse,
)
from app.routes import (
    app_auth,
    app_dashboard,
    app_qr,
    app_payments,
    app_history,
    app_legal,
)
from .utils import now_local, today_local, month_start, end_of_month, in_time_window, generate_token, next_passenger_code
from app.qr_helpers import make_qr_png, create_or_rotate_token
from fastapi.middleware.cors import CORSMiddleware
from app.routers.app_payments_webpay import router as app_payments_webpay_router
from app.auth_helpers import security, get_passenger_from_token

app = FastAPI(title="Ecobus MVP Control Pasajeros", version="0.1.0")

app.include_router(app_payments_webpay_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ecobus-passenger-app.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_auth.router)
app.include_router(app_dashboard.router)
app.include_router(app_qr.router)
app.include_router(app_payments.router)
app.include_router(app_history.router)
app.include_router(app_legal.router)


# Create tables automatically (MVP friendly). In production, switch to Alembic migrations.
Base.metadata.create_all(bind=ENGINE)
def _ensure_plan_enum_values():
    """
    Asegura que el enum existente 'plantype' tenga los nuevos valores.
    Se ejecuta al iniciar la API.
    """
    stmts = [
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_10';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_20';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_30';",
        "ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'VIAJES_40';",
    ]

    try:
        # ALTER TYPE requiere AUTOCOMMIT en Postgres
        with ENGINE.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as e:
        # No botamos la app por esto; solo registramos advertencia.
        print("WARN: no se pudo asegurar enum plantype:", repr(e))


_ensure_plan_enum_values()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Ecobus MVP Control Pasajeros",
        "scan_url": "/scan",
        "docs": "/docs",
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/scan", response_class=HTMLResponse)
def scan_page(pin: str | None = None):
    # Simple PIN gate (mobile-first). Scanner can bookmark /scan?pin=XXXX
    if pin != settings.scanner_pin:
        return HTMLResponse(
            """
            <html><head><meta name='viewport' content='width=device-width, initial-scale=1' />
            <title>Scanner</title>
            <style>
              body{font-family:system-ui, -apple-system, Segoe UI, Roboto, Arial; padding:24px;}
              input{font-size:18px; padding:12px; width:100%; max-width:280px;}
              button{font-size:18px; padding:12px 16px; margin-top:12px;}
              .box{max-width:420px}
            </style></head>
            <body>
              <div class='box'>
                <h2>Acceso Scanner</h2>
                <p>Ingresa PIN para abrir el scanner.</p>
                <input id='pin' placeholder='PIN' inputmode='numeric' />
                <button onclick="location.href='/scan?pin='+encodeURIComponent(document.getElementById('pin').value)">Entrar</button>
              </div>
            </body></html>
            """,
            status_code=401,
        )
    # Serve static scanner app
    with open("static/scan.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/q/{token}")
def token_landing(token: str):
    # Passenger QR encodes this URL. When scanned, the scanner extracts token from URL.
    # If someone opens it in a browser, show a friendly message.
    return HTMLResponse(
        f"""
        <html><head><meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>QR Ecobus</title>
        <style>body{{font-family:system-ui; padding:24px;}}</style></head>
        <body>
          <h2>QR Ecobus</h2>
          <p>Este QR es para validación al subir al bus.</p>
          <p><b>Token:</b> {token}</p>
        </body></html>
        """
    )
@app.get("/ot/{token}")
def one_time_landing(token: str):
    return HTMLResponse(
        f"""
        <html><head><meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>QR Pase Diario</title>
        <style>body{{font-family:system-ui; padding:24px;}}</style></head>
        <body>
          <h2>QR Pase Diario</h2>
          <p>Este QR es de un solo uso.</p>
          <p><b>Token:</b> {token}</p>
        </body></html>
        """
    )

# ---------- Passengers ----------

@app.post("/api/passengers", response_model=PassengerOut)
def create_passenger(payload: PassengerCreate):
    with get_db() as db:
        code = next_passenger_code(db)
        p = Passenger(
            code=code,
            full_name=payload.full_name.strip(),
            phone=payload.phone.strip(),
            email=str(payload.email) if payload.email else None,
            pickup_point_default=payload.pickup_point_default,
            is_active=payload.is_active,
        )
        db.add(p)
        db.flush()
        # Create initial active token for current month
        create_or_rotate_token(db, p.id)
        db.refresh(p)
        return PassengerOut(
            id=str(p.id),
            code=p.code,
            full_name=p.full_name,
            phone=p.phone,
            email=p.email,
            pickup_point_default=p.pickup_point_default,
            is_active=p.is_active,
        )


@app.get("/api/passengers", response_model=list[PassengerOut])
def search_passengers(query: str | None = None):
    with get_db() as db:
        stmt = select(Passenger)
        if query:
            q = f"%{query.strip()}%"
            stmt = stmt.where(
                (Passenger.full_name.ilike(q))
                | (Passenger.phone.ilike(q))
                | (Passenger.code.ilike(q))
            )
        stmt = stmt.order_by(Passenger.created_at.desc()).limit(100)
        rows = db.execute(stmt).scalars().all()
        return [
            PassengerOut(
                id=str(p.id),
                code=p.code,
                full_name=p.full_name,
                phone=p.phone,
                email=p.email,
                pickup_point_default=p.pickup_point_default,
                is_active=p.is_active,
            )
            for p in rows
        ]


@app.patch("/api/passengers/{passenger_id}", response_model=PassengerOut)
def update_passenger(passenger_id: str, payload: PassengerUpdate):
    with get_db() as db:
        p = db.get(Passenger, passenger_id)
        if not p:
            raise HTTPException(404, "Passenger not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(p, k, v)
        db.add(p)
        db.flush()
        db.refresh(p)
        return PassengerOut(
            id=str(p.id),
            code=p.code,
            full_name=p.full_name,
            phone=p.phone,
            email=p.email,
            pickup_point_default=p.pickup_point_default,
            is_active=p.is_active,
        )


# ---------- QR regen ----------

@app.post("/api/passengers/{passenger_id}/qr/regen")
def regen_qr(passenger_id: str):
    with get_db() as db:
        p = db.get(Passenger, passenger_id)
        if not p:
            raise HTTPException(404, "Passenger not found")
        token = create_or_rotate_token(db, p.id)
        png_bytes = make_qr_png(f"{settings.public_base_url.rstrip('/')}/q/{token}")
        return Response(content=png_bytes, media_type="image/png")


# ---------- Subscriptions activation ----------

@app.post("/api/subscriptions/activate")
def activate_subscription(payload: ActivateSubscriptionIn):
    with get_db() as db:
        p = db.execute(
            select(Passenger).where(Passenger.code == payload.passenger_code)
        ).scalar_one_or_none()
        if not p:
            raise HTTPException(404, "Passenger not found")

        PLAN_RIDES = {
            PlanType.VIAJES_10: 10,
            PlanType.VIAJES_20: 20,
            PlanType.VIAJES_30: 30,
            PlanType.VIAJES_40: 40,
        }

        # Solo planes nuevos (sin IDA/VUELTA/IDA_VUELTA)
        if payload.plan_type not in PLAN_RIDES:
            raise HTTPException(400, "PlanType inválido (usa VIAJES_10/20/30/40)")

        rides_included = PLAN_RIDES[payload.plan_type]

        sub = db.execute(
            select(Subscription).where(
                and_(Subscription.passenger_id == p.id, Subscription.month == payload.month)
            )
        ).scalar_one_or_none()

        if not sub:
            sub = Subscription(
                passenger_id=p.id,
                month=payload.month,
                plan_type=payload.plan_type,
                payment_status=payload.payment_status,
                rides_included=rides_included,
                rides_used_ida=0,
                rides_used_vuelta=0,
                activated_at=now_local().replace(tzinfo=None),
                notes=payload.notes,
            )
        else:
            sub.plan_type = payload.plan_type
            sub.payment_status = payload.payment_status
            sub.rides_included = rides_included
            sub.activated_at = now_local().replace(tzinfo=None)
            sub.notes = payload.notes

        db.add(sub)

        # Rotar token al activar plan
        create_or_rotate_token(db, p.id)

        return {"ok": True, "message": "Suscripción activada y QR rotado."}


# ---------- Daily passes ----------

@app.post("/api/daily_passes")
def create_daily_pass(payload: DailyPassCreate):
    with get_db() as db:
        p = db.execute(select(Passenger).where(Passenger.code == payload.passenger_code)).scalar_one_or_none()
        if not p:
            raise HTTPException(404, "Passenger not found")
        dp = DailyPass(
            passenger_id=p.id,
            service_date=payload.service_date,
            trip_type=payload.trip_type,
            payment_status=payload.payment_status,
            reservation_status=payload.reservation_status,
        )
        db.add(dp)
        db.flush()
        return {"ok": True, "id": dp.id}


@app.patch("/api/daily_passes/{daily_pass_id}")
def update_daily_pass(daily_pass_id: int, payload: DailyPassUpdate):
    with get_db() as db:
        dp = db.get(DailyPass, daily_pass_id)
        if not dp:
            raise HTTPException(404, "Daily pass not found")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(dp, k, v)
        db.add(dp)
        return {"ok": True}


# ---------- Validation ----------
@app.get("/api/validate", response_model=ValidateResponse)
def validate(
    token: str = Query(...),
    trip_type: TripType = Query(...),
    pickup_point: PickupPoint = Query(...),
):
    with get_db() as db:
        # token exists and active
        t = db.execute(select(QrToken).where(QrToken.token == token)).scalar_one_or_none()
        now = now_local()
        service_date = now.date()

        # ---- 1) SI NO ES TOKEN MENSUAL, PROBAR TOKEN ONE-TIME (PASE DIARIO) ----
        if not t:
            ot = db.execute(select(OneTimeToken).where(OneTimeToken.token == token)).scalar_one_or_none()

            if not ot:
                _log_checkin(db, None, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "TOKEN_INVALIDO", entitlement=None)
                return ValidateResponse(result="REJECTED", reason="TOKEN_INVALIDO", message="Token inválido o no existe.")

            if ot.status != OneTimeTokenStatus.ACTIVE or ot.used_at is not None:
                _log_checkin(db, ot.passenger_id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "TOKEN_USADO", entitlement="DAILY_PASS")
                return ValidateResponse(result="REJECTED", reason="TOKEN_USADO", message="QR ya fue utilizado.")

            p_ot = db.get(Passenger, ot.passenger_id)
            if not p_ot or not p_ot.is_active:
                _log_checkin(db, ot.passenger_id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "PLAN_INACTIVO", entitlement="DAILY_PASS")
                return ValidateResponse(result="REJECTED", reason="PLAN_INACTIVO", message="Pasajero inactivo.")

            dp = db.get(DailyPass, ot.daily_pass_id)
            if not dp:
                _log_checkin(db, p_ot.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "SIN_DERECHO_A_VIAJE", entitlement="DAILY_PASS")
                return ValidateResponse(
                    result="REJECTED",
                    full_name=p_ot.full_name,
                    code=p_ot.code,
                    reason="SIN_DERECHO_A_VIAJE",
                    message="No existe pase diario asociado a este QR.",
                )

            # Revalidación de seguridad (aunque el QR se genera solo con pago confirmado)
            if dp.payment_status != PaymentStatus.PAGADO or dp.reservation_status != ReservationStatus.CONFIRMADO:
                _log_checkin(db, p_ot.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "PASE_NO_CONFIRMADO", entitlement="DAILY_PASS")
                return ValidateResponse(
                    result="REJECTED",
                    full_name=p_ot.full_name,
                    code=p_ot.code,
                    reason="PASE_NO_CONFIRMADO",
                    message="Pase diario no pagado o no confirmado.",
                )

            # El pase diario debe coincidir con el tipo de viaje seleccionado en el scanner
            if dp.trip_type != trip_type:
                _log_checkin(db, p_ot.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "TOKEN_TIPO", entitlement="DAILY_PASS")
                return ValidateResponse(
                    result="REJECTED",
                    full_name=p_ot.full_name,
                    code=p_ot.code,
                    reason="TOKEN_TIPO",
                    message="Este QR no corresponde a este tipo de viaje (IDA/VUELTA).",
                )

            # Consumir token (1 uso)
            ot.status = OneTimeTokenStatus.USED
            ot.used_at = now.replace(tzinfo=None)
            db.add(ot)

            _log_checkin(db, p_ot.id, service_date, trip_type, pickup_point, CheckinResult.OK, None, entitlement="DAILY_PASS")

            return ValidateResponse(
                result="OK",
                full_name=p_ot.full_name,
                code=p_ot.code,
                plan="PASE_DIARIO",
                month=month_start(service_date),
                pickup_point=pickup_point.value,
                message="Pase diario OK. QR consumido (1 uso).",
            )

        if not t or t.status != TokenStatus.ACTIVE:
            _log_checkin(db, None, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "TOKEN_INVALIDO")
            return ValidateResponse(result="REJECTED", reason="TOKEN_INVALIDO", message="Token inválido o revocado.")

        # validity window
        valid_from = t.valid_from.replace(tzinfo=ZoneInfo(settings.tz))
        valid_to = t.valid_to.replace(tzinfo=ZoneInfo(settings.tz))
        if not (valid_from <= now <= valid_to):
            _log_checkin(db, None, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "TOKEN_INVALIDO")
            return ValidateResponse(result="REJECTED", reason="TOKEN_INVALIDO", message="Token fuera de vigencia.")

        p = db.get(Passenger, t.passenger_id)
        if not p or not p.is_active:
            _log_checkin(db, t.passenger_id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "PLAN_INACTIVO")
            return ValidateResponse(
                result="REJECTED",
                full_name=p.full_name if p else None,
                code=p.code if p else None,
                reason="PLAN_INACTIVO",
                message="Pasajero inactivo.",
            )

                # time window (can be disabled for testing)
        if not settings.disable_time_window:
            nt = now.timetz().replace(tzinfo=None)

            if trip_type == TripType.IDA:
                if not in_time_window(nt, settings.time_window_ida_start, settings.time_window_ida_end):
                    _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "FUERA_DE_HORARIO")
                    return ValidateResponse(
                        result="REJECTED",
                        full_name=p.full_name,
                        code=p.code,
                        reason="FUERA_DE_HORARIO",
                        message="Escaneo fuera de horario permitido.",
                    )
            else:
                if not in_time_window(nt, settings.time_window_vuelta_start, settings.time_window_vuelta_end):
                    _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "FUERA_DE_HORARIO")
                    return ValidateResponse(
                        result="REJECTED",
                        full_name=p.full_name,
                        code=p.code,
                        reason="FUERA_DE_HORARIO",
                        message="Escaneo fuera de horario permitido.",
                    )

        # anti-duplicate
        cutoff = now.replace(tzinfo=None)  # stored naive
        recent_from = cutoff - __import__("datetime").timedelta(minutes=settings.duplicate_minutes)
        dup = db.execute(
            select(Checkin)
            .where(
                and_(
                    Checkin.passenger_id == p.id,
                    Checkin.service_date == service_date,
                    Checkin.trip_type == trip_type,
                    Checkin.result == CheckinResult.OK,
                    Checkin.created_at >= recent_from,
                )
            )
            .order_by(Checkin.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if dup:
            _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "DUPLICADO_RECIENTE")
            return ValidateResponse(
                result="REJECTED",
                full_name=p.full_name,
                code=p.code,
                reason="DUPLICADO_RECIENTE",
                message="Escaneo duplicado reciente.",
            )

        # eligibility: subscription (priority) then daily pass
        ms = month_start(service_date)
        sub = db.execute(
            select(Subscription).where(
                and_(Subscription.passenger_id == p.id, Subscription.month == ms)
            )
        ).scalar_one_or_none()

        if sub and sub.payment_status == PaymentStatus.PAGADO:
            if not _plan_allows(sub.plan_type, trip_type):
                _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "PLAN_NO_PERMITE_VIAJE")
                return ValidateResponse(
                    result="REJECTED",
                    full_name=p.full_name,
                    code=p.code,
                    reason="PLAN_NO_PERMITE_VIAJE",
                    message="Plan no permite este tipo de viaje.",
                )

            if not _has_rides_left(sub, trip_type):
                _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "RIDES_AGOTADOS")
                return ValidateResponse(
                    result="REJECTED",
                    full_name=p.full_name,
                    code=p.code,
                    reason="RIDES_AGOTADOS",
                    message="Viajes del plan agotados.",
                )

            _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.OK, None)
            _consume_ride(sub, trip_type)
            db.add(sub)

            used_total = sub.rides_used_ida + sub.rides_used_vuelta
            remaining = max(0, sub.rides_included - used_total)

            return ValidateResponse(
                result="OK",
                full_name=p.full_name,
                code=p.code,
                plan=sub.plan_type.value,
                month=sub.month,
                pickup_point=pickup_point.value,
                rides_included=sub.rides_included,
                rides_used_total=used_total,
                rides_remaining=remaining,
                message="Pasajero activo. Check-in registrado.",
            )

        # daily pass path
        dp = db.execute(
            select(DailyPass).where(
                and_(
                    DailyPass.passenger_id == p.id,
                    DailyPass.service_date == service_date,
                    DailyPass.trip_type == trip_type,
                )
            )
        ).scalar_one_or_none()

        if not dp:
            _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "SIN_DERECHO_A_VIAJE")
            return ValidateResponse(
                result="REJECTED",
                full_name=p.full_name,
                code=p.code,
                reason="SIN_DERECHO_A_VIAJE",
                message="Sin plan activo ni pase diario.",
            )

        if dp.payment_status != PaymentStatus.PAGADO or dp.reservation_status != ReservationStatus.CONFIRMADO:
            _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "PASE_NO_CONFIRMADO")
            return ValidateResponse(
                result="REJECTED",
                full_name=p.full_name,
                code=p.code,
                reason="PASE_NO_CONFIRMADO",
                message="Pase diario no pagado o no confirmado.",
            )

        confirmed_count = db.execute(
            select(func.count()).select_from(DailyPass).where(
                and_(
                    DailyPass.service_date == service_date,
                    DailyPass.trip_type == trip_type,
                    DailyPass.payment_status == PaymentStatus.PAGADO,
                    DailyPass.reservation_status == ReservationStatus.CONFIRMADO,
                )
            )
        ).scalar_one()

        if confirmed_count > settings.daily_reserved:
            _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.REJECTED, "SIN_CUPO")
            return ValidateResponse(
                result="REJECTED",
                full_name=p.full_name,
                code=p.code,
                reason="SIN_CUPO",
                message="Sin cupo disponible para pase diario.",
            )

        _log_checkin(db, p.id, service_date, trip_type, pickup_point, CheckinResult.OK, None)
        return ValidateResponse(
            result="OK",
            full_name=p.full_name,
            code=p.code,
            plan="PASE_DIARIO",
            month=ms,
            pickup_point=pickup_point.value,
            message="Pase diario confirmado. Check-in registrado.",
        )


def _log_checkin(db, passenger_id, service_date, trip_type, pickup_point, result, reason, entitlement: str | None = None):
    c = Checkin(
        created_at=now_local().replace(tzinfo=None),
        service_date=service_date,
        trip_type=trip_type,
        pickup_point=pickup_point,
        passenger_id=passenger_id,
        result=result,
        reason=reason,
        entitlement=entitlement,
    )
    db.add(c)

def _plan_allows(plan_type: PlanType, trip_type: TripType) -> bool:
    if plan_type in (PlanType.VIAJES_10, PlanType.VIAJES_20, PlanType.VIAJES_30, PlanType.VIAJES_40):
        return True

    # Compatibilidad con planes antiguos
    if plan_type == PlanType.IDA_VUELTA:
        return True
    if plan_type == PlanType.IDA and trip_type == TripType.IDA:
        return True
    if plan_type == PlanType.VUELTA and trip_type == TripType.VUELTA:
        return True
    return False



def _has_rides_left(sub: Subscription, trip_type: TripType) -> bool:
    # strict control of rides_included
    used_total = sub.rides_used_ida + sub.rides_used_vuelta
    if used_total >= sub.rides_included:
        return False
    # optional: also per-direction control could go here
    return True


def _consume_ride(sub: Subscription, trip_type: TripType) -> None:
    if trip_type == TripType.IDA:
        sub.rides_used_ida += 1
    else:
        sub.rides_used_vuelta += 1


# ---------- Simple reporting endpoints (used by admin or external) ----------

@app.get("/api/checkins/day")
def checkins_day(service_date: str | None = None):
    with get_db() as db:
        d = today_local() if not service_date else __import__("datetime").date.fromisoformat(service_date)
        rows = db.execute(
            select(Checkin, Passenger)
            .join(Passenger, Passenger.id == Checkin.passenger_id, isouter=True)
            .where(Checkin.service_date == d)
            .order_by(desc(Checkin.created_at))
        ).all()
        out = []
        for c, p in rows:
            out.append(
                {
                    "created_at": c.created_at.isoformat(),
                    "service_date": c.service_date.isoformat(),
                    "trip_type": c.trip_type.value,
                    "pickup_point": c.pickup_point.value,
                    "result": c.result.value,
                    "reason": c.reason,
                    "code": p.code if p else None,
                    "full_name": p.full_name if p else None,
                }
            )
        return {"date": d.isoformat(), "items": out}

from sqlalchemy import text

@app.get("/__run_migration_auth")
def run_auth_migration():
    stmts = [
        """
        ALTER TABLE passengers
        ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP NULL,
        ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP NULL,
        ADD COLUMN IF NOT EXISTS app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP NULL,
        ADD COLUMN IF NOT EXISTS accepted_terms_version VARCHAR(50) NULL,
        ADD COLUMN IF NOT EXISTS accepted_terms_at TIMESTAMP NULL;
        """,
        "DROP TABLE IF EXISTS otp_codes CASCADE;",
        "DROP TABLE IF EXISTS user_sessions CASCADE;",
        """
        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            passenger_id UUID NULL REFERENCES passengers(id),
            identifier VARCHAR(200) NOT NULL,
            channel VARCHAR(20) NOT NULL,
            code_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_otp_codes_passenger_id ON otp_codes(passenger_id);",
        "CREATE INDEX IF NOT EXISTS ix_otp_codes_identifier ON otp_codes(identifier);",
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            passenger_id UUID NOT NULL REFERENCES passengers(id),
            token_hash VARCHAR(255) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            device_info TEXT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_passenger_id ON user_sessions(passenger_id);",
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash ON user_sessions(token_hash);",
    ]

    with get_db() as db:
        for stmt in stmts:
            db.execute(text(stmt))
        db.commit()

    return {"ok": True, "message": "Migración ejecutada correctamente"}
