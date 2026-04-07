import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select, and_, desc, func
from app.models import OneTimeToken, OneTimeTokenStatus

from app.config import settings
from app.db import get_db, ENGINE
from app.models import (
    Base,
    Passenger,
    Subscription,
    DailyPass,
    Checkin,
    PickupPoint,
    TripType,
    PlanType,
    PaymentStatus,
    ReservationStatus,
    QrToken,
    TokenStatus,
    CheckinResult,
    TransferRequest,
    TransferRequestStatus,
    TransferRequestType,
    OneTimeToken,
    OneTimeTokenStatus,
    Service, 
    ServiceCode,
)
from app.main import make_qr_png, create_or_rotate_token
from app.utils import now_local

Base.metadata.create_all(bind=ENGINE)

st.set_page_config(page_title="Ecobus Admin", layout="wide")
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "ecobus_logo.png"


def inject_ecobus_admin_styles():
    st.markdown(
        """
        <style>
            :root {
                --ecobus-green: #5ca52f;
                --ecobus-green-dark: #3e7b22;
                --ecobus-green-soft: #eef7e8;
                --ecobus-green-pale: #f6fbf2;
                --ecobus-border: #dce9d2;
                --ecobus-text: #183222;
                --ecobus-muted: #5f6f63;
            }

            .stApp {
                background: linear-gradient(180deg, #f6fbf2 0%, #f9fbf8 100%);
            }

            .ecobus-topbar {
                height: 14px;
                width: 100%;
                background: linear-gradient(90deg, #3e7b22 0%, #5ca52f 50%, #7bc043 100%);
                border-radius: 14px;
                margin-bottom: 14px;
                box-shadow: 0 6px 18px rgba(92, 165, 47, 0.20);
            }

            .ecobus-hero {
                display: flex;
                align-items: center;
                gap: 22px;
                background: #ffffff;
                border: 1px solid var(--ecobus-border);
                border-radius: 18px;
                padding: 22px 26px;
                margin-bottom: 22px;
                box-shadow: 0 12px 28px rgba(0, 0, 0, 0.06);
            }

            .ecobus-logo-wrap {
                flex: 0 0 auto;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(180deg, #f7fbf3 0%, #edf6e6 100%);
                border: 1px solid var(--ecobus-border);
                border-radius: 16px;
                padding: 14px 18px;
                min-width: 220px;
            }

            .ecobus-logo-fallback {
                font-size: 32px;
                font-weight: 900;
                color: var(--ecobus-green-dark);
                letter-spacing: 1px;
            }

            .ecobus-hero-text {
                flex: 1;
            }

            .ecobus-hero-kicker {
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: var(--ecobus-green);
                margin-bottom: 6px;
            }

            .ecobus-hero-title {
                margin: 0;
                font-size: 34px;
                line-height: 1.05;
                font-weight: 900;
                color: var(--ecobus-green-dark);
            }

            .ecobus-hero-subtitle {
                margin-top: 8px;
                font-size: 15px;
                color: var(--ecobus-muted);
                line-height: 1.45;
            }

            .ecobus-hero-badges {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 14px;
            }

            .ecobus-badge {
                display: inline-flex;
                align-items: center;
                padding: 8px 12px;
                border-radius: 999px;
                background: var(--ecobus-green-soft);
                border: 1px solid var(--ecobus-border);
                color: var(--ecobus-green-dark);
                font-size: 13px;
                font-weight: 700;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 10px;
                margin-top: 2px;
                margin-bottom: 12px;
            }

            .stTabs [data-baseweb="tab"] {
                background: #ffffff;
                border-radius: 12px;
                border: 1px solid var(--ecobus-border);
                padding: 10px 16px;
                color: var(--ecobus-text);
                font-weight: 700;
                box-shadow: 0 2px 8px rgba(0,0,0,0.02);
            }

            .stTabs [aria-selected="true"] {
                background: var(--ecobus-green-soft) !important;
                border-color: var(--ecobus-green) !important;
                color: var(--ecobus-green-dark) !important;
            }

            .stButton > button {
                border-radius: 10px;
                border: 1px solid var(--ecobus-green);
                background: #f1f8ea;
                color: var(--ecobus-green-dark);
                font-weight: 800;
            }

            .stButton > button:hover {
                border-color: var(--ecobus-green-dark);
                background: #e6f2db;
                color: var(--ecobus-green-dark);
            }

            div[data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid var(--ecobus-border);
                border-radius: 14px;
                padding: 12px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.03);
            }

            div[data-testid="stDataFrame"] {
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid #e5eee0;
                background: #ffffff;
            }

            .ecobus-section-title {
                color: var(--ecobus-green-dark);
                font-weight: 900;
                font-size: 25px;
                margin-top: 8px;
                margin-bottom: 10px;
            }

            @media (max-width: 900px) {
                .ecobus-hero {
                    flex-direction: column;
                    align-items: flex-start;
                }

                .ecobus-logo-wrap {
                    min-width: unset;
                    width: 100%;
                }

                .ecobus-hero-title {
                    font-size: 28px;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_ecobus_header():
    st.markdown('<div class="ecobus-topbar"></div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1.15, 3.2], gap="medium")

    with col1:
        st.markdown('<div class="ecobus-logo-wrap">', unsafe_allow_html=True)
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=230)
        else:
            st.markdown('<div class="ecobus-logo-fallback">ECOBUS</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown(
            """
            <div class="ecobus-hero">
                <div class="ecobus-hero-text">
                    <div class="ecobus-hero-kicker">Panel corporativo</div>
                    <h1 class="ecobus-hero-title">Ecobus Admin</h1>
                    <div class="ecobus-hero-subtitle">
                        Gestión operativa, control de pasajeros, seguimiento de pagos
                        y administración centralizada del servicio.
                    </div>
                    <div class="ecobus-hero-badges">
                        <span class="ecobus-badge">Operación diaria</span>
                        <span class="ecobus-badge">Pagos y transferencias</span>
                        <span class="ecobus-badge">Control de planes y pases</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

inject_ecobus_admin_styles()
render_ecobus_header()

    with get_db() as db:
        service_rows = db.execute(
            select(Service).where(Service.is_active == True).order_by(Service.name.asc())
        ).scalars().all()

    service_options = ["TODOS"] + [s.code.value for s in service_rows]
    service_labels = {"TODOS": "Todos"} | {s.code.value: s.name for s in service_rows}

    selected_service_code = st.selectbox(
        "Servicio",
        options=service_options,
        format_func=lambda x: service_labels.get(x, x),
        index=0,
        key="global_service_filter",
    )

if "last_transfer_qr_png" not in st.session_state:
    st.session_state.last_transfer_qr_png = None

if "last_transfer_qr_filename" not in st.session_state:
    st.session_state.last_transfer_qr_filename = None

if "last_transfer_qr_url" not in st.session_state:
    st.session_state.last_transfer_qr_url = None


def download_df(df: pd.DataFrame, fname: str):
    st.download_button(
        label=f"Descargar {fname}",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
    )


PLAN_PRICES = {
    "VIAJES_10": 19000,
    "VIAJES_20": 35000,
    "VIAJES_30": 49000,
    "VIAJES_40": 60000,
}


# =========================
# TABS (UI ordenada)
# =========================

tabs = st.tabs([
    "Dashboard día",
    "Pasajeros",
    "Planes mensuales",
    "Pase diario",
    "Finanzas",
    "Transferencias pendientes",
    "Historial transferencias",
])


def render_dashboard_dia():
    st.markdown('<div class="ecobus-section-title">Dashboard día</div>', unsafe_allow_html=True)

    d = st.date_input("Fecha de servicio", value=date.today(), key="dash_date")

    with get_db() as db:
        rows = db.execute(
            select(Checkin, Passenger)
            .join(Passenger, Passenger.id == Checkin.passenger_id, isouter=True)
            .where(Checkin.service_date == d)
            .order_by(desc(Checkin.created_at))
        ).all()

    data = []
    for c, p in rows:
        data.append({
            "hora": c.created_at.strftime("%H:%M:%S") if c.created_at else None,
            "fecha": c.service_date.isoformat() if c.service_date else None,
            "trip_type": c.trip_type.value if c.trip_type else None,
            "pickup_point": c.pickup_point.value if c.pickup_point else None,
            "resultado": c.result.value if c.result else None,
            "razon": c.reason,
            "entitlement": getattr(c, "entitlement", None) or "—",
            "codigo": p.code if p else None,
            "nombre": p.full_name if p else None,
        })

    df = pd.DataFrame(data)

    if df.empty:
        st.info("Sin check-ins para la fecha seleccionada.")
        return

    if "entitlement" not in df.columns:
        df["entitlement"] = "—"

    col1, col2, col3, col4, col5 = st.columns(5)

    ok = (df["resultado"] == "OK").sum()
    rej = (df["resultado"] == "REJECTED").sum()
    monthly_ok = ((df["resultado"] == "OK") & (df["entitlement"] == "MONTHLY")).sum()
    daily_ok = ((df["resultado"] == "OK") & (df["entitlement"] == "DAILY_PASS")).sum()

    col1.metric("OK", int(ok))
    col2.metric("OK (Plan)", int(monthly_ok))
    col3.metric("OK (Pase diario)", int(daily_ok))
    col4.metric("RECHAZADOS", int(rej))
    col5.metric("TOTAL", int(len(df)))

    st.dataframe(df, use_container_width=True)
    download_df(df, f"checkins_{d.isoformat()}.csv")

    st.markdown("#### Pases diarios (OK)")
    df_daily_ok = df[(df["resultado"] == "OK") & (df["entitlement"] == "DAILY_PASS")]
    if df_daily_ok.empty:
        st.info("No hay check-ins OK con Pase Diario.")
    else:
        st.dataframe(df_daily_ok, use_container_width=True)

    st.markdown("#### Rechazados por razón")
    st.dataframe(
        df[df["resultado"] == "REJECTED"]["razon"]
          .value_counts()
          .reset_index()
          .rename(columns={"index": "razon", "razon": "conteo"}),
        use_container_width=True
    )

def render_pasajeros():
    st.markdown('<div class="ecobus-section-title">Pasajeros</div>', unsafe_allow_html=True)

    colA, colB = st.columns([2, 1])
    with colA:
        q = st.text_input("Buscar por nombre / teléfono / código", key="p_search")
    with colB:
        show_inactive = st.checkbox("Incluir inactivos", value=True, key="p_show_inactive")

    with get_db() as db:
        stmt = select(Passenger)
        stmt = stmt.where(Passenger.is_deleted == False)
        
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                (Passenger.full_name.ilike(like)) |
                (Passenger.phone.ilike(like)) |
                (Passenger.code.ilike(like))
            )
        if not show_inactive:
            stmt = stmt.where(Passenger.is_active == True)
            stmt = stmt.where(Passenger.is_deleted == False)

        passengers = db.execute(stmt.order_by(desc(Passenger.created_at)).limit(200)).scalars().all()

        passenger_rows = [{
            "id": str(p.id),
            "code": p.code,
            "full_name": p.full_name,
            "phone": p.phone,
            "email": p.email,
            "pickup_default": p.pickup_point_default.value if p.pickup_point_default else None,
            "active": bool(p.is_active),
        } for p in passengers]

    st.write(f"Resultados: {len(passenger_rows)}")
    if passenger_rows:
        dfp = pd.DataFrame(passenger_rows)
        st.dataframe(dfp, use_container_width=True)

    st.markdown("### Eliminar pasajero (soft-delete)")

    del_code = st.text_input("Código a eliminar (ej: ECO0001)", key="del_pass_code").strip().upper()
    confirm = st.checkbox("Confirmo que quiero eliminarlo", key="del_pass_confirm")
    btn_del = st.button("🗑️ Eliminar pasajero", type="primary")

    if btn_del:
        if not del_code or not confirm:
            st.error("Ingresa código y confirma.")
        else:
            with get_db() as db:
                p = db.execute(select(Passenger).where(Passenger.code == del_code)).scalar_one_or_none()
                if not p:
                    st.error("No existe ese pasajero.")
                else:
                    p.is_deleted = True
                    p.deleted_at = now_local().replace(tzinfo=None)
                    db.add(p)
            st.success("Pasajero eliminado (soft-delete). Ya no contará en Finanzas ni listas.")

    st.markdown("---")
    st.markdown("### Acciones sobre pasajero")

    action_code = st.text_input("Código pasajero (ej: ECO0001)", key="action_code").strip().upper()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        btn_deactivate = st.button("Desactivar", use_container_width=True)
    with col2:
        btn_reactivate = st.button("Reactivar", use_container_width=True)
    with col3:
        btn_qr_download = st.button("Descargar QR vigente", use_container_width=True)
    with col4:
        btn_qr_regen = st.button("Regenerar + Descargar QR", use_container_width=True)

    if btn_deactivate or btn_reactivate:
        if not action_code:
            st.error("Ingresa un código de pasajero")
        else:
            with get_db() as db:
                p = db.execute(select(Passenger).where(Passenger.code == action_code)).scalar_one_or_none()
                if not p:
                    st.error("No existe pasajero con ese código")
                else:
                    p.is_active = False if btn_deactivate else True
                    db.add(p)
                    create_or_rotate_token(db, p.id)
            st.success("Acción aplicada correctamente.")

    if btn_qr_download or btn_qr_regen:
        if not action_code:
            st.error("Ingresa un código de pasajero")
        else:
            with get_db() as db:
                p = db.execute(select(Passenger).where(Passenger.code == action_code)).scalar_one_or_none()
                if not p:
                    st.error("No existe pasajero con ese código")
                else:
                    token = None

                    if btn_qr_regen:
                        token = create_or_rotate_token(db, p.id)
                    else:
                        t = db.execute(
                            select(QrToken).where(
                                and_(QrToken.passenger_id == p.id, QrToken.status == TokenStatus.ACTIVE)
                            ).order_by(desc(QrToken.valid_to))
                        ).scalar_one_or_none()

                        if t:
                            now_naive = now_local().replace(tzinfo=None)
                            if t.valid_from <= now_naive <= t.valid_to:
                                token = t.token

                        if not token:
                            token = create_or_rotate_token(db, p.id)

                    qr_url = f"{settings.public_base_url.rstrip('/')}/q/{token}"
                    png_bytes = make_qr_png(qr_url)

            st.download_button(
                label="Descargar PNG QR",
                data=png_bytes,
                file_name=f"QR_{action_code}.png",
                mime="image/png",
            )

    st.markdown("---")
    st.markdown("## Detalle de pasajero")

    detail_code = st.text_input("Código pasajero para ver detalle (ej: ECO0001)", key="detail_code").strip().upper()
    month_for_detail = st.date_input(
        "Mes a revisar (usar 1er día del mes)",
        value=date(date.today().year, date.today().month, 1),
        key="detail_month",
    )

    if detail_code:
        p_data = None
        sub_data = None
        checkin_rows = []

        month_start_dt = datetime.combine(month_for_detail, datetime.min.time())
        next_month = (month_for_detail.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end_dt = datetime.combine(next_month, datetime.min.time())

        with get_db() as db:
            p = db.execute(select(Passenger).where(Passenger.code == detail_code)).scalar_one_or_none()
            if not p:
                st.error("No existe pasajero con ese código")
            else:
                p_data = {
                    "id": p.id,
                    "code": p.code,
                    "full_name": p.full_name,
                    "phone": p.phone,
                    "email": p.email,
                    "pickup_default": p.pickup_point_default.value if p.pickup_point_default else None,
                    "is_active": bool(p.is_active),
                }

                sub = db.execute(
                    select(Subscription).where(
                        and_(Subscription.passenger_id == p.id, Subscription.month == month_for_detail)
                    )
                ).scalar_one_or_none()

                if sub:
                    used_total = (sub.rides_used_ida or 0) + (sub.rides_used_vuelta or 0)
                    remaining = max(0, (sub.rides_included or 0) - used_total)
                    plan_name = sub.plan_type.value if sub.plan_type else None

                    sub_data = {
                        "plan": plan_name,
                        "payment_status": sub.payment_status.value if sub.payment_status else None,
                        "rides_included": sub.rides_included,
                        "rides_used_ida": sub.rides_used_ida,
                        "rides_used_vuelta": sub.rides_used_vuelta,
                        "rides_used_total": used_total,
                        "rides_remaining": remaining,
                        "activated_at": sub.activated_at,
                        "notes": sub.notes,
                    }

                checkins = db.execute(
                    select(Checkin)
                    .where(
                        and_(
                            Checkin.passenger_id == p.id,
                            Checkin.created_at >= month_start_dt,
                            Checkin.created_at < month_end_dt,
                        )
                    )
                    .order_by(desc(Checkin.created_at))
                    .limit(300)
                ).scalars().all()

                for c in checkins:
                    checkin_rows.append({
                        "fecha_hora": c.created_at.isoformat(sep=" ", timespec="seconds") if c.created_at else None,
                        "service_date": c.service_date.isoformat() if c.service_date else None,
                        "trip_type": c.trip_type.value if c.trip_type else None,
                        "pickup_point": c.pickup_point.value if c.pickup_point else None,
                        "resultado": c.result.value if c.result else None,
                        "razon": c.reason,
                    })

        if p_data:
            st.markdown("### Resumen / Status")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Activo", "Sí" if p_data["is_active"] else "No")
            col2.metric("Punto default", p_data["pickup_default"] or "—")

            if sub_data:
                col3.metric("Plan", sub_data["plan"] or "—")
                col4.metric("Restantes", str(sub_data["rides_remaining"]))
            else:
                col3.metric("Plan", "Sin plan")
                col4.metric("Restantes", "—")

            st.markdown("### Pago / Renovación")
            pay_col1, pay_col2, pay_col3 = st.columns(3)

            if sub_data:
                plan_name = sub_data["plan"] or ""
                amount = PLAN_PRICES.get(plan_name, 0)

                paid_when = sub_data["activated_at"].isoformat(sep=" ", timespec="minutes") if sub_data["activated_at"] else "—"
                paid_at = sub_data["activated_at"]
                base_dt = paid_at if paid_at else datetime.now()
                next_due_dt = base_dt + timedelta(days=30)
                next_due = next_due_dt.strftime("%Y-%m-%d %H:%M")
                days_left = (next_due_dt.date() - datetime.now().date()).days

                pay_col1.metric("Estado de pago", sub_data["payment_status"] or "—")
                pay_col2.metric("Pagó (activado)", paid_when)
                pay_col3.metric("Próximo pago", next_due)
                st.caption(f"Días restantes para renovar: {days_left}")

                if amount:
                    st.info(f"Monto plan: ${amount:,} CLP".replace(",", "."))
            else:
                st.info("Este pasajero no tiene plan para el mes seleccionado.")

            st.markdown("### Viajes (check-ins) del mes")
            if checkin_rows:
                dfc = pd.DataFrame(checkin_rows)

                ok_count = (dfc["resultado"] == "OK").sum()
                rej_count = (dfc["resultado"] == "REJECTED").sum()

                colA, colB, colC = st.columns(3)
                colA.metric("OK", int(ok_count))
                colB.metric("RECHAZADOS", int(rej_count))
                colC.metric("TOTAL", int(len(dfc)))

                st.dataframe(dfc, use_container_width=True)
                download_df(dfc, f"checkins_{p_data['code']}_{month_for_detail.isoformat()}.csv")

                st.markdown("#### Rechazos por razón")
                st.dataframe(
                    dfc[dfc["resultado"] == "REJECTED"]["razon"]
                      .value_counts()
                      .reset_index()
                      .rename(columns={"index": "razon", "razon": "conteo"}),
                    use_container_width=True
                )
            else:
                st.info("Sin check-ins registrados en el mes seleccionado para este pasajero.")

    st.markdown("---")
    st.markdown("### Crear pasajero")

    with st.form("create_passenger"):
        full_name = st.text_input("Nombre completo")
        phone = st.text_input("Teléfono")
        email = st.text_input("Email (opcional)")
        pickup = st.selectbox("Punto de subida default", [pp.value for pp in PickupPoint])
        is_active = st.checkbox("Activo", value=True)
        submitted = st.form_submit_button("Crear")

    if submitted:
        if not full_name.strip() or not phone.strip():
            st.error("Nombre y teléfono son obligatorios")
        else:
            from app.utils import next_passenger_code

            with get_db() as db:
                code = next_passenger_code(db)
                p = Passenger(
                    code=code,
                    full_name=full_name.strip(),
                    phone=phone.strip(),
                    email=email.strip() or None,
                    pickup_point_default=PickupPoint(pickup),
                    is_active=is_active,
                )
                db.add(p)
                db.flush()

                passenger_code = p.code
                passenger_id = str(p.id)

                create_or_rotate_token(db, p.id)

            st.success(f"Pasajero creado: {passenger_code}")
            st.info(f"QR generado. Puedes descargarlo desde Acciones con el código {passenger_code}.")
            st.caption(f"ID interno: {passenger_id}")


def render_planes_mensuales():
    st.markdown('<div class="ecobus-section-title">Planes Mensuales</div>', unsafe_allow_html=True)
    
    mode = st.radio(
        "Modo de visualización",
        ["Vigentes hoy", "Mes calendario"],
        horizontal=True,
        key="subs_view_mode",
    )


    month = st.date_input(
        "Mes (usar 1er día del mes)",
        value=date(date.today().year, date.today().month, 1),
        key="subs_month",
    )

    with get_db() as db:
        if mode == "Vigentes hoy":
            now_dt = now_local().replace(tzinfo=None)
            subs = db.execute(
                select(Subscription, Passenger)
                .join(Passenger, Passenger.id == Subscription.passenger_id)
                .where(Subscription.is_deleted == False)
                .where(Subscription.payment_status == PaymentStatus.PAGADO)
                .where(Subscription.activated_at != None)
                .where(Subscription.expires_at != None)
                .where(Subscription.activated_at <= now_dt)
                .where(Subscription.expires_at >= now_dt)
                .order_by(Passenger.code)
            ).all()
        else:
            subs = db.execute(
                select(Subscription, Passenger)
                .join(Passenger, Passenger.id == Subscription.passenger_id)
                .where(Subscription.month == month)
                .where(Subscription.is_deleted == False)
                .order_by(Passenger.code)
            ).all()

    subs_rows = []
    for s, p in subs:
        used_total = (s.rides_used_ida or 0) + (s.rides_used_vuelta or 0)
        remaining = max(0, (s.rides_included or 0) - used_total)
        subs_rows.append({
            "sub_id": s.id,
            "passenger_code": p.code,
            "full_name": p.full_name,
            "plan_type": s.plan_type.value if s.plan_type else None,
            "payment_status": s.payment_status.value if s.payment_status else None,
            "rides_included": s.rides_included,
            "rides_used_ida": s.rides_used_ida,
            "rides_used_vuelta": s.rides_used_vuelta,
            "rides_used_total": used_total,
            "rides_remaining": remaining,
            "activated_at": s.activated_at,
            "expires_at": s.expires_at,
        })

    if subs_rows:
        dfs = pd.DataFrame(subs_rows)
        st.dataframe(dfs, use_container_width=True)
        st.markdown("---")
        st.markdown("### Eliminar plan mensual (soft-delete)")

        sub_id = st.number_input("ID del plan (sub_id)", min_value=1, step=1, key="del_sub_id")
        confirm_sub = st.checkbox("Confirmo eliminar este plan", key="del_sub_confirm")
        btn_del_sub = st.button("🗑️ Eliminar plan", key="btn_del_sub", type="primary")

        if btn_del_sub:
            if not confirm_sub:
                st.error("Confirma la eliminación.")
            else:
                with get_db() as db:
                    sub = db.get(Subscription, int(sub_id))
                    if not sub:
                        st.error("No existe ese plan (sub_id).")
                    else:
                        sub.is_deleted = True
                        sub.deleted_at = now_local().replace(tzinfo=None)
                        db.add(sub)
                st.success("Plan eliminado (soft-delete).")
        download_df(dfs, f"subs_{month.isoformat()}.csv")
    else:
        st.info("Sin planes para este mes.")

    st.markdown("---")
    st.markdown("### Activar / Actualizar plan (manual por pago)")

    with st.form("activate_sub"):
        passenger_code = st.text_input("Código pasajero (ej: ECO0001)", key="sub_code").strip().upper()
        plan_type = st.selectbox(
            "Tipo de plan",
            [PlanType.VIAJES_10.value, PlanType.VIAJES_20.value, PlanType.VIAJES_30.value, PlanType.VIAJES_40.value],
        )
        pay_status = st.selectbox("Estado de pago", [ps.value for ps in PaymentStatus], index=0)
        reset_usage = st.checkbox("Resetear uso del mes (dejar usados en 0)", value=False)
        notes = st.text_area("Notas (opcional)")
        ok = st.form_submit_button("Guardar")

    if ok:
        PLAN_RIDES = {"VIAJES_10": 10, "VIAJES_20": 20, "VIAJES_30": 30, "VIAJES_40": 40}
        rides_included = PLAN_RIDES[plan_type]

        with get_db() as db:
            p = db.execute(select(Passenger).where(Passenger.code == passenger_code)).scalar_one_or_none()
            if not p:
                st.error("No existe pasajero")
            else:
                sub = db.execute(
                    select(Subscription).where(and_(Subscription.passenger_id == p.id, Subscription.month == month))
                ).scalar_one_or_none()

                if not sub:
                    sub = Subscription(
                        passenger_id=p.id,
                        month=month,
                        plan_type=PlanType(plan_type),
                        payment_status=PaymentStatus(pay_status),
                        rides_included=rides_included,
                        rides_used_ida=0,
                        rides_used_vuelta=0,
                        activated_at=now_local().replace(tzinfo=None),
                        notes=notes or None,
                    )
                else:
                    sub.plan_type = PlanType(plan_type)
                    sub.payment_status = PaymentStatus(pay_status)
                    sub.rides_included = rides_included
                    sub.activated_at = now_local().replace(tzinfo=None)
                    sub.notes = notes or None
                    if reset_usage:
                        sub.rides_used_ida = 0
                        sub.rides_used_vuelta = 0

                db.add(sub)
                create_or_rotate_token(db, p.id)

        st.success("Plan guardado y QR rotado.")


def render_pase_diario():
    st.markdown('<div class="ecobus-section-title">Pase Diario</div>', unsafe_allow_html=True)

    d = st.date_input("Fecha", value=date.today(), key="dp_date")
    trip = st.selectbox("Tipo de viaje", [t.value for t in TripType], key="dp_trip")

    # Tabla de pases del día
    with get_db() as db:
        rows = db.execute(
            select(DailyPass, Passenger)
            .join(Passenger, Passenger.id == DailyPass.passenger_id)
            .where(and_(DailyPass.service_date == d, DailyPass.trip_type == TripType(trip)))
            .order_by(Passenger.code)
        ).all()

    daily_rows = []
    for dp, p in rows:
        daily_rows.append({
            "id": dp.id,
            "passenger_code": p.code,
            "full_name": p.full_name,
            "payment_status": dp.payment_status.value,
            "reservation_status": dp.reservation_status.value,
        })

    if daily_rows:
        dfd = pd.DataFrame(daily_rows)
        st.dataframe(dfd, use_container_width=True)
        download_df(dfd, f"daily_pass_{d.isoformat()}_{trip}.csv")
    else:
        st.info("Sin pases para la selección.")

    st.markdown("---")
    st.markdown("### Crear solicitud (Pase diario)")

    with st.form("dp_create"):
        passenger_code = st.text_input("Código pasajero", key="dp_code").strip().upper()
        pay_status = st.selectbox("Estado de pago", [ps.value for ps in PaymentStatus], key="dp_pay")
        res_status = st.selectbox("Estado reserva", [rs.value for rs in ReservationStatus], key="dp_res")
        ok = st.form_submit_button("Crear")

    # ✅ ESTE BLOQUE DEBE ESTAR DENTRO DE LA FUNCIÓN
    if ok:
        png_bytes = None
        qr_fname = None

        with get_db() as db:
            p = db.execute(select(Passenger).where(Passenger.code == passenger_code)).scalar_one_or_none()
            if not p:
                st.error("No existe pasajero")
                return

            dp = DailyPass(
                passenger_id=p.id,
                service_date=d,
                trip_type=TripType(trip),
                payment_status=PaymentStatus(pay_status),
                reservation_status=ReservationStatus(res_status),
            )
            db.add(dp)
            db.flush()  # dp.id disponible

            # Generar QR 1-uso SOLO si ya está pagado + confirmado
            if PaymentStatus(pay_status) == PaymentStatus.PAGADO and ReservationStatus(res_status) == ReservationStatus.CONFIRMADO:
                from app.models import OneTimeToken, OneTimeTokenStatus
                from app.utils import generate_token

                token = generate_token()
                ot = OneTimeToken(
                    passenger_id=p.id,
                    daily_pass_id=dp.id,
                    token=token,
                    service_date=d,
                    trip_type=TripType(trip),
                    status=OneTimeTokenStatus.ACTIVE,
                )
                db.add(ot)
                db.flush()

                qr_url = f"{settings.public_base_url.rstrip('/')}/ot/{token}"
                png_bytes = make_qr_png(qr_url)
                qr_fname = f"QR_PASE_DIARIO_{passenger_code}_{d.isoformat()}_{trip}.png"

        if png_bytes:
            st.success("Pase diario creado (PAGADO+CONFIRMADO) + QR 1 uso generado.")
            st.download_button(
                label="Descargar QR Pase Diario (PNG)",
                data=png_bytes,
                file_name=qr_fname,
                mime="image/png",
            )
            st.caption(f"Link QR: {settings.public_base_url.rstrip('/')}/ot/{token}")
        else:
            st.success("Solicitud creada. Cuando esté PAGADO + CONFIRMADO, genera el QR.")


def _plan_rides_from_type(plan_type_value: str) -> int:
    plan_map = {
        "VIAJES_10": 10,
        "VIAJES_20": 20,
        "VIAJES_30": 30,
        "VIAJES_40": 40,
    }
    if plan_type_value not in plan_map:
        raise ValueError(f"Plan no soportado: {plan_type_value}")
    return plan_map[plan_type_value]


def _approve_transfer_request(db, tr: TransferRequest, admin_note: str | None = None):
    if tr.status != TransferRequestStatus.PENDING:
        raise ValueError("La solicitud ya fue revisada.")

    payload = tr.payload or {}
    passenger = db.get(Passenger, tr.passenger_id)
    if not passenger:
        raise ValueError("No existe el pasajero asociado a la solicitud.")

    qr_result = None

    if tr.request_type == TransferRequestType.MONTHLY:
        month_raw = payload.get("month")
        plan_type_raw = payload.get("plan_type")

        if not month_raw or not plan_type_raw:
            raise ValueError("Payload incompleto para transferencia mensual.")

        month_value = date.fromisoformat(month_raw)
        plan_enum = PlanType[plan_type_raw]
        rides_included = _plan_rides_from_type(plan_type_raw)

        sub = db.execute(
            select(Subscription).where(
                and_(
                    Subscription.passenger_id == passenger.id,
                    Subscription.month == month_value,
                    Subscription.is_deleted == False,
                )
            )
        ).scalar_one_or_none()

        if not sub:
            sub = Subscription(
                passenger_id=passenger.id,
                month=month_value,
                plan_type=plan_enum,
                payment_status=PaymentStatus.PAGADO,
                rides_included=rides_included,
                rides_used_ida=0,
                rides_used_vuelta=0,
                activated_at=now_local().replace(tzinfo=None),
                notes="Aprobado por transferencia manual",
            )
        else:
            sub.plan_type = plan_enum
            sub.payment_status = PaymentStatus.PAGADO
            sub.rides_included = rides_included
            sub.activated_at = now_local().replace(tzinfo=None)
            prev = sub.notes or ""
            sub.notes = (prev + "\n" if prev else "") + "Actualizado por aprobación de transferencia manual"

        db.add(sub)
        create_or_rotate_token(db, passenger.id)

    elif tr.request_type == TransferRequestType.DAILY:
        service_date_raw = payload.get("service_date")
        trip_type_raw = payload.get("trip_type")

        if not service_date_raw or not trip_type_raw:
            raise ValueError("Payload incompleto para transferencia de pase diario.")

        service_date_value = date.fromisoformat(service_date_raw)
        trip_type_enum = TripType(trip_type_raw)

        dp = db.execute(
            select(DailyPass).where(
                and_(
                    DailyPass.passenger_id == passenger.id,
                    DailyPass.service_date == service_date_value,
                    DailyPass.trip_type == trip_type_enum,
                    DailyPass.is_deleted == False,
                )
            )
        ).scalar_one_or_none()

        if not dp:
            dp = DailyPass(
                passenger_id=passenger.id,
                service_date=service_date_value,
                trip_type=trip_type_enum,
                payment_status=PaymentStatus.PAGADO,
                reservation_status=ReservationStatus.CONFIRMADO,
            )
            db.add(dp)
            db.flush()
        else:
            dp.payment_status = PaymentStatus.PAGADO
            dp.reservation_status = ReservationStatus.CONFIRMADO
            db.add(dp)
            db.flush()

        existing_ot = db.execute(
            select(OneTimeToken).where(
                and_(
                    OneTimeToken.daily_pass_id == dp.id,
                    OneTimeToken.status == OneTimeTokenStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()

        if existing_ot:
            token = existing_ot.token
        else:
            from app.utils import generate_token

            token = generate_token()
            ot = OneTimeToken(
                passenger_id=passenger.id,
                daily_pass_id=dp.id,
                token=token,
                service_date=service_date_value,
                trip_type=trip_type_enum,
                status=OneTimeTokenStatus.ACTIVE,
            )
            db.add(ot)
            db.flush()

        qr_url = f"{settings.public_base_url.rstrip('/')}/ot/{token}"
        png_bytes = make_qr_png(qr_url)
        qr_fname = f"QR_PASE_DIARIO_{passenger.code}_{service_date_value.isoformat()}_{trip_type_enum.value}.png"

        qr_result = {
            "png_bytes": png_bytes,
            "filename": qr_fname,
            "url": qr_url,
        }

    else:
        raise ValueError("Tipo de transferencia no soportado.")

    tr.status = TransferRequestStatus.APPROVED
    tr.reviewed_at = now_local().replace(tzinfo=None)
    tr.reviewed_by = "admin_streamlit"
    tr.admin_notes = admin_note or None
    db.add(tr)

    return qr_result


def _reject_transfer_request(db, tr: TransferRequest, admin_note: str | None = None):
    if tr.status != TransferRequestStatus.PENDING:
        raise ValueError("La solicitud ya fue revisada.")

    tr.status = TransferRequestStatus.REJECTED
    tr.reviewed_at = now_local().replace(tzinfo=None)
    tr.reviewed_by = "admin_streamlit"
    tr.admin_notes = admin_note or None
    db.add(tr)


def render_transferencias_pendientes():
    st.markdown('<div class="ecobus-section-title">Transferencias Pendientes</div>', unsafe_allow_html=True)

    if st.session_state.last_transfer_qr_png:
        st.success("Último QR de pase diario generado correctamente.")
        st.download_button(
            label="Descargar último QR generado (PNG)",
            data=st.session_state.last_transfer_qr_png,
            file_name=st.session_state.last_transfer_qr_filename or "qr_pase_diario.png",
            mime="image/png",
            key="download_last_transfer_qr",
        )
        if st.session_state.last_transfer_qr_url:
            st.caption(f"Link QR: {st.session_state.last_transfer_qr_url}")

    with get_db() as db:
        rows = db.execute(
            select(TransferRequest, Passenger)
            .join(Passenger, Passenger.id == TransferRequest.passenger_id)
            .where(TransferRequest.status == TransferRequestStatus.PENDING)
            .order_by(TransferRequest.created_at.asc(), TransferRequest.id.asc())
        ).all()

    if not rows:
        st.success("No hay transferencias pendientes.")
        return

    st.write(f"Pendientes: {len(rows)}")

    for tr, p in rows:
        with st.container(border=True):
            st.markdown(f"### Solicitud #{tr.id}")
            c1, c2, c3 = st.columns(3)

            with c1:
                st.write(f"**Pasajero:** {p.full_name}")
                st.write(f"**Código:** {p.code}")

            with c2:
                st.write(f"**Tipo:** {tr.request_type.value}")
                st.write(f"**Fecha solicitud:** {tr.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

            with c3:
                st.write(f"**Estado:** {tr.status.value}")
                st.write(f"**Email:** {p.email or '—'}")

            st.markdown("**Payload:**")
            st.json(tr.payload)

            if tr.notes:
                st.markdown(f"**Nota pasajero:** {tr.notes}")

            admin_note = st.text_area(
                "Nota admin",
                key=f"tr_admin_note_{tr.id}",
                placeholder="Opcional: observación interna",
            )

            col_a, col_b = st.columns(2)

            with col_a:
                if st.button(f"Aprobar #{tr.id}", key=f"approve_transfer_{tr.id}", use_container_width=True):
                    try:
                        with get_db() as db:
                            tr_db = db.get(TransferRequest, tr.id)
                            if not tr_db:
                                st.error("La solicitud ya no existe.")
                            else:
                                qr_result = _approve_transfer_request(db, tr_db, admin_note)

                                if qr_result:
                                    st.session_state.last_transfer_qr_png = qr_result["png_bytes"]
                                    st.session_state.last_transfer_qr_filename = qr_result["filename"]
                                    st.session_state.last_transfer_qr_url = qr_result["url"]
                                else:
                                    st.session_state.last_transfer_qr_png = None
                                    st.session_state.last_transfer_qr_filename = None
                                    st.session_state.last_transfer_qr_url = None
                        st.success(f"Solicitud #{tr.id} aprobada correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al aprobar solicitud #{tr.id}: {e}")

            with col_b:
                if st.button(f"Rechazar #{tr.id}", key=f"reject_transfer_{tr.id}", use_container_width=True):
                    try:
                        with get_db() as db:
                            tr_db = db.get(TransferRequest, tr.id)
                            if not tr_db:
                                st.error("La solicitud ya no existe.")
                            else:
                                _reject_transfer_request(db, tr_db, admin_note)
                        st.warning(f"Solicitud #{tr.id} rechazada.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al rechazar solicitud #{tr.id}: {e}")

def render_historial_transferencias():
    st.markdown('<div class="ecobus-section-title">Historial de Transferencias</div>', unsafe_allow_html=True)

    status_filter = st.selectbox(
        "Filtrar por estado",
        ["TODAS", "APPROVED", "REJECTED"],
        index=0,
        key="transfer_history_status_filter",
    )

    with get_db() as db:
        stmt = (
            select(TransferRequest, Passenger)
            .join(Passenger, Passenger.id == TransferRequest.passenger_id)
            .order_by(desc(TransferRequest.created_at), desc(TransferRequest.id))
        )

        if status_filter != "TODAS":
            stmt = stmt.where(TransferRequest.status == TransferRequestStatus(status_filter))
        else:
            stmt = stmt.where(
                TransferRequest.status.in_([
                    TransferRequestStatus.APPROVED,
                    TransferRequestStatus.REJECTED,
                ])
            )

        rows = db.execute(stmt).all()

    if not rows:
        st.info("No hay transferencias en el historial para ese filtro.")
        return

    data = []
    for tr, p in rows:
        data.append({
            "id": tr.id,
            "fecha_solicitud": tr.created_at.strftime("%Y-%m-%d %H:%M:%S") if tr.created_at else None,
            "estado": tr.status.value,
            "tipo": tr.request_type.value,
            "codigo": p.code,
            "pasajero": p.full_name,
            "email": p.email,
            "reviewed_at": tr.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if tr.reviewed_at else None,
            "reviewed_by": tr.reviewed_by,
            "nota_pasajero": tr.notes,
            "nota_admin": tr.admin_notes,
            "payload": str(tr.payload),
        })

    dft = pd.DataFrame(data)
    st.dataframe(dft, use_container_width=True)
    download_df(dft, "historial_transferencias.csv")

def render_finanzas():
    st.markdown('<div class="ecobus-section-title">Finanzas</div>', unsafe_allow_html=True)

    PLAN_PRICES = {
        "VIAJES_10": 19000,
        "VIAJES_20": 35000,
        "VIAJES_30": 49000,
        "VIAJES_40": 60000,
    }

    st.markdown("### Período")
    mode = st.radio(
        "Tipo de reporte",
        ["Mes calendario (por Subscription.month)", "Últimos 30 días (por activated_at)"],
        horizontal=True,
        key="fin_mode",
    )

    today = date.today()

    if mode.startswith("Mes calendario"):
        month = st.date_input(
            "Mes a revisar (usar 1er día del mes)",
            value=date(today.year, today.month, 1),
            key="fin_month",
        )
        start_dt = datetime.combine(month, datetime.min.time())
        # fin del mes
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_dt = datetime.combine(next_month, datetime.min.time())
    else:
        days = st.slider("Ventana (días)", 7, 60, 30, key="fin_days")
        end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time())
        start_dt = end_dt - timedelta(days=days)
        month = date(today.year, today.month, 1)  # para acciones por mes, si hace falta

    st.caption(f"Rango: {start_dt.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')}")

    # -------------------------
    # PASES DIARIOS (FINANZAS)
    # -------------------------
    st.markdown("---")
    st.markdown("### Pases diarios (CLP $2.000 c/u)")

    DAILY_PASS_PRICE = 2000

    with get_db() as db:
        # Pases vendidos = PAGADO + CONFIRMADO dentro del rango
        dp_rows = db.execute(
            select(DailyPass, Passenger)
            .join(Passenger, Passenger.id == DailyPass.passenger_id)
            .where(
                and_(
                    DailyPass.service_date >= start_dt.date(),
                    DailyPass.service_date < end_dt.date(),
                    DailyPass.payment_status == PaymentStatus.PAGADO,
                    DailyPass.reservation_status == ReservationStatus.CONFIRMADO,
                    DailyPass.is_deleted == False,
                )
            )
            .where(Passenger.is_deleted == False)
            .order_by(DailyPass.service_date.desc(), Passenger.code)
            
        ).all()

    dp_table = []
    for dp, p in dp_rows:
        dp_table.append({
            "service_date": dp.service_date.isoformat() if dp.service_date else None,
            "trip_type": dp.trip_type.value if dp.trip_type else None,
            "passenger_code": p.code,
            "full_name": p.full_name,
            "monto_clp": DAILY_PASS_PRICE,
        })

    df_dp = pd.DataFrame(dp_table)

    dp_count = int(len(df_dp))
    dp_total = int(dp_count * DAILY_PASS_PRICE)

    c1, c2, c3 = st.columns(3)
    c1.metric("Pases diarios (conteo)", str(dp_count))
    c2.metric("Ingresos pases diarios (CLP)", f"${dp_total:,}".replace(",", "."))
    c3.metric("Precio unitario", f"${DAILY_PASS_PRICE:,}".replace(",", "."))

    if dp_count:
        st.dataframe(df_dp, use_container_width=True)
        download_df(df_dp, f"pases_diarios_{start_dt.date().isoformat()}_{end_dt.date().isoformat()}.csv")

        st.markdown("#### Ventas por día (pases diarios)")
        by_day = (
            df_dp.groupby("service_date")["monto_clp"]
            .sum()
            .reset_index()
            .sort_values("service_date")
        )
        st.line_chart(by_day.set_index("service_date"))
    else:
        st.info("No hay pases diarios PAGADO + CONFIRMADO en el período.")
    
    st.markdown("---")
    st.markdown("### KPIs del período")

    with get_db() as db:
        # Traemos subs + pasajero para cálculos en Python
        if mode.startswith("Mes calendario"):
            subs = db.execute(
                select(Subscription, Passenger)
                .join(Passenger, Passenger.id == Subscription.passenger_id)
                .where(Subscription.month == month)
                .order_by(Passenger.code)
            ).all()
        else:
            # últimos N días: por activated_at (si activated_at es None no entra)
            subs = db.execute(
                select(Subscription, Passenger)
                .join(Passenger, Passenger.id == Subscription.passenger_id)
                .where(and_(Subscription.activated_at != None,
                            Subscription.activated_at >= start_dt,
                            Subscription.activated_at < end_dt))
                .where(Subscription.is_deleted == False)
                .where(Passenger.is_deleted == False)
                .order_by(Subscription.activated_at.desc())
            ).all()

    rows = []
    for s, p in subs:
        plan = s.plan_type.value if s.plan_type else None
        price = PLAN_PRICES.get(plan, 0)

        paid = (s.payment_status == PaymentStatus.PAGADO)
        status = s.payment_status.value if s.payment_status else None

        activated_at = s.activated_at
        next_due_dt = None
        days_left = None
        if activated_at:
            next_due_dt = activated_at + timedelta(days=30)
            days_left = (next_due_dt.date() - today).days

        used_total = (s.rides_used_ida or 0) + (s.rides_used_vuelta or 0)
        remaining = max(0, (s.rides_included or 0) - used_total)

        rows.append({
            "passenger_code": p.code,
            "full_name": p.full_name,
            "plan": plan,
            "price": price,
            "payment_status": status,
            "activated_at": activated_at,
            "next_due": next_due_dt,
            "days_left": days_left,
            "rides_included": s.rides_included,
            "rides_used_total": used_total,
            "rides_remaining": remaining,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        st.info("Sin suscripciones para el período seleccionado.")
        return

    # KPIs
    total_plans = len(df)
    total_sold = int(df["price"].sum())

    paid_df = df[df["payment_status"] == "PAGADO"]
    pending_df = df[df["payment_status"] != "PAGADO"]

    total_paid = int(paid_df["price"].sum())
    total_pending = int(pending_df["price"].sum())
    avg_ticket = int(total_sold / total_plans) if total_plans else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Planes (conteo)", str(total_plans))
    k2.metric("Vendido (CLP)", f"${total_sold:,}".replace(",", "."))
    k3.metric("Pagado (CLP)", f"${total_paid:,}".replace(",", "."))
    k4.metric("Pendiente (CLP)", f"${total_pending:,}".replace(",", "."))

    st.caption(f"Ticket promedio: ${avg_ticket:,} CLP".replace(",", "."))

    st.markdown("---")
    st.markdown("### Distribución de planes")
    dist = df.groupby("plan", dropna=False).agg(
        planes=("plan", "count"),
        vendido=("price", "sum"),
        pagado=("price", lambda x: int(df.loc[x.index][df.loc[x.index, "payment_status"] == "PAGADO"]["price"].sum())),
    ).reset_index()

    st.dataframe(dist, use_container_width=True)

    st.markdown("---")
    st.markdown("### Renovaciones (activated_at + 30 días)")

    horizon = st.slider("Mostrar vencimientos dentro de (días)", 1, 60, 14, key="fin_horizon")
    renew_df = df[df["next_due"].notna()].copy()
    renew_df["days_left"] = renew_df["days_left"].astype(int)

    due_soon = renew_df[(renew_df["days_left"] <= horizon)]
    due_soon = due_soon.sort_values("days_left")

    colA, colB, colC = st.columns(3)
    colA.metric(f"Vencen en ≤ {horizon} días", str(len(due_soon)))
    colB.metric("Vencidos (≤ 0 días)", str(len(renew_df[renew_df["days_left"] <= 0])))
    colC.metric("Pagados en lista", str(len(due_soon[due_soon["payment_status"] == "PAGADO"])))

    if len(due_soon):
        st.dataframe(
            due_soon[[
                "passenger_code", "full_name", "plan", "payment_status",
                "activated_at", "next_due", "days_left", "rides_remaining"
            ]],
            use_container_width=True
        )
        download_df(due_soon, f"renovaciones_{today.isoformat()}.csv")
    else:
        st.info("No hay renovaciones próximas en el horizonte seleccionado.")

    st.markdown("---")
    st.markdown("### Ingresos diarios (Pagado)")

    # gráfico simple por día usando activated_at
    gdf = df[df["payment_status"] == "PAGADO"].copy()
    gdf = gdf[gdf["activated_at"].notna()]
    if not gdf.empty:
        gdf["day"] = pd.to_datetime(gdf["activated_at"]).dt.date
        by_day = gdf.groupby("day")["price"].sum().reset_index()
        by_day = by_day.sort_values("day")
        st.line_chart(by_day.set_index("day"))
    else:
        st.info("No hay activaciones pagadas en el período para graficar.")

    st.markdown("---")
    st.markdown("### Acciones (operación financiera)")

    st.caption("Estas acciones editan la suscripción del pasajero para el mes seleccionado (Subscription.month).")

    action_month = st.date_input(
        "Mes objetivo (usar 1er día del mes)",
        value=date(today.year, today.month, 1),
        key="fin_action_month",
    )

    with st.form("fin_actions"):
        passenger_code = st.text_input("Código pasajero (ej: ECO0001)", key="fin_pass_code").strip().upper()
        new_rides = st.number_input("Ajustar rides_included (nuevo total)", min_value=0, value=20, step=1)
        new_pay_status = st.selectbox("Estado de pago", [ps.value for ps in PaymentStatus], index=0)
        touch_activated = st.checkbox("Actualizar activated_at a ahora (para iniciar vigencia 30 días)", value=False)
        reason = st.text_area("Motivo / nota (obligatorio para auditoría)", key="fin_reason")
        apply = st.form_submit_button("Aplicar cambios")

    if apply:
        if not passenger_code:
            st.error("Falta código de pasajero.")
        elif not reason.strip():
            st.error("Debes escribir un motivo para el cambio (auditoría).")
        else:
            with get_db() as db:
                p = db.execute(select(Passenger).where(Passenger.code == passenger_code)).scalar_one_or_none()
                if not p:
                    st.error("No existe pasajero con ese código.")
                else:
                    sub = db.execute(
                        select(Subscription).where(
                            and_(Subscription.passenger_id == p.id, Subscription.month == action_month)
                        )
                    ).scalar_one_or_none()

                    if not sub:
                        st.error("El pasajero no tiene plan creado para ese mes. Créalo en 'Planes mensuales'.")
                    else:
                        # Ajustes
                        sub.rides_included = int(new_rides)
                        sub.payment_status = PaymentStatus(new_pay_status)
                        if touch_activated:
                            sub.activated_at = now_local().replace(tzinfo=None)

                        # auditoría simple en notes
                        stamp = now_local().replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
                        audit_line = f"[FIN {stamp}] rides_included={new_rides}, payment={new_pay_status}, touch_activated={touch_activated}. Motivo: {reason.strip()}"
                        sub.notes = (sub.notes + "\n" + audit_line) if sub.notes else audit_line

                        db.add(sub)

                        st.success("Cambios aplicados.")

with tabs[0]:
    render_dashboard_dia()

with tabs[1]:
    render_pasajeros()

with tabs[2]:
    render_planes_mensuales()

with tabs[3]:
    render_pase_diario()

with tabs[4]:
    render_finanzas()

with tabs[5]:
    render_transferencias_pendientes()

with tabs[6]:
    render_historial_transferencias()

st.markdown("---")
st.caption("Config: Render + Postgres recomendado. TZ y ventanas horarias desde variables de entorno.")
