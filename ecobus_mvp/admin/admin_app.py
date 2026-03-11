import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import select, func, and_, desc
from sqlalchemy import text

from app.config import settings
from app.db import get_db, ENGINE
from app.models import Base, Passenger, Subscription, DailyPass, Checkin, PickupPoint, TripType, PlanType, PaymentStatus, ReservationStatus

Base.metadata.create_all(bind=ENGINE)

st.set_page_config(page_title="Ecobus Admin", layout="wide")
st.title("Ecobus / Ecovan - Admin MVP")
st.caption("Panel operativo mínimo (MVP).")


def download_df(df: pd.DataFrame, fname: str):
    st.download_button(
        label=f"Descargar {fname}",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
    )


tabs = st.tabs(["Dashboard día", "Pasajeros", "Planes mensuales", "Pase diario"])

with tabs[0]:
    st.subheader("Dashboard día")
    d = st.date_input("Fecha de servicio", value=date.today())

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
                "codigo": p.code if p else None,
                "nombre": p.full_name if p else None,
            })

    df = pd.DataFrame(data)

    if df.empty:
        st.info("Sin check-ins para la fecha seleccionada.")
    else:
        col1, col2, col3 = st.columns(3)
        ok = (df["resultado"] == "OK").sum()
        rej = (df["resultado"] == "REJECTED").sum()
        col1.metric("OK", int(ok))
        col2.metric("RECHAZADOS", int(rej))
        col3.metric("TOTAL", int(len(df)))

        st.dataframe(df, use_container_width=True)
        download_df(df, f"checkins_{d.isoformat()}.csv")

        st.markdown("#### Rechazados por razón")
        st.dataframe(
            df[df["resultado"] == "REJECTED"]["razon"]
              .value_counts()
              .reset_index()
              .rename(columns={"index": "razon", "razon": "conteo"}),
            use_container_width=True
        )

with tabs[1]:
    st.subheader("Pasajeros")

    colA, colB = st.columns([2, 1])
    with colA:
        q = st.text_input("Buscar por nombre / teléfono / código")
    with colB:
        show_inactive = st.checkbox("Incluir inactivos", value=True)

    with get_db() as db:
        stmt = select(Passenger)

        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                (Passenger.full_name.ilike(like)) |
                (Passenger.phone.ilike(like)) |
                (Passenger.code.ilike(like))
            )

        if not show_inactive:
            stmt = stmt.where(Passenger.is_active == True)

        passengers = db.execute(
            stmt.order_by(desc(Passenger.created_at)).limit(200)
        ).scalars().all()

        passenger_rows = []
        for p in passengers:
            passenger_rows.append({
                "id": str(p.id),
                "code": p.code,
                "full_name": p.full_name,
                "phone": p.phone,
                "email": p.email,
                "pickup_default": p.pickup_point_default.value if p.pickup_point_default else None,
                "active": p.is_active,
            })

    st.write(f"Resultados: {len(passenger_rows)}")

    if passenger_rows:
        dfp = pd.DataFrame(passenger_rows)
        st.dataframe(dfp, use_container_width=True)
        st.markdown("---")
st.markdown("## Detalle de pasajero")

detail_code = st.text_input("Código pasajero para ver detalle (ej: ECO0001)", key="detail_code").strip().upper()
month_for_detail = st.date_input(
    "Mes a revisar (usar 1er día del mes)",
    value=date(date.today().year, date.today().month, 1),
    key="detail_month",
)

# (Opcional) precios por plan (si no quieres montos, elimina esto)
PLAN_PRICES = {
    "VIAJES_10": 18500,
    "VIAJES_20": 35000,
    "VIAJES_30": 49000,
    "VIAJES_40": 60000,
}

if detail_code:
    p_data = None
    sub_data = None
    checkin_rows = []

    # calcular rango del mes
    month_start_dt = datetime.combine(month_for_detail, datetime.min.time())
    next_month = (month_for_detail.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end_dt = datetime.combine(next_month, datetime.min.time())

    with get_db() as db:
        p = db.execute(select(Passenger).where(Passenger.code == detail_code)).scalar_one_or_none()
        if not p:
            st.error("No existe pasajero con ese código")
        else:
            # pasa el pasajero a dict (evita DetachedInstanceError)
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

            # checkins a dict
            for c in checkins:
                checkin_rows.append({
                    "fecha_hora": c.created_at.isoformat(sep=" ", timespec="seconds") if c.created_at else None,
                    "service_date": c.service_date.isoformat() if c.service_date else None,
                    "trip_type": c.trip_type.value if c.trip_type else None,
                    "pickup_point": c.pickup_point.value if c.pickup_point else None,
                    "resultado": c.result.value if c.result else None,
                    "razon": c.reason,
                })

    # si no hay pasajero, p_data queda None y ya mostramos error arriba
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
            next_due = next_month.isoformat()

            pay_col1.metric("Estado de pago", sub_data["payment_status"] or "—")
            pay_col2.metric("Pagó (activado)", paid_when)
            pay_col3.metric("Próximo pago", next_due)

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


        # ---- ACCIONES (nuevo) ----
        st.markdown("---")
        st.markdown("### Acciones sobre pasajero")

        action_code = st.text_input("Código pasajero (ej: ECO0001)", key="action_code").strip().upper()

        col1, col2 = st.columns(2)
        with col1:
            btn_deactivate = st.button("Desactivar pasajero", use_container_width=True)
        with col2:
            btn_reactivate = st.button("Reactivar pasajero", use_container_width=True)
            from app.config import settings
from app.models import QrToken, TokenStatus
from app.main import _make_qr_png, _create_or_rotate_token
from app.utils import now_local

col3, col4 = st.columns(2)
with col3:
    btn_qr_download = st.button("Descargar QR (vigente)", use_container_width=True)
with col4:
    btn_qr_regen = st.button("Regenerar y descargar QR", use_container_width=True)

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
                    # crea/rota token nuevo del mes
                    token = _create_or_rotate_token(db, p.id)
                else:
                    # busca token activo vigente
                    t = db.execute(
                        select(QrToken).where(
                            and_(
                                QrToken.passenger_id == p.id,
                                QrToken.status == TokenStatus.ACTIVE,
                            )
                        )
                        .order_by(QrToken.valid_to.desc())
                    ).scalar_one_or_none()

                    if t:
                        # valid_to está guardado naive; lo comparamos naive
                        now_naive = now_local().replace(tzinfo=None)
                        if t.valid_from <= now_naive <= t.valid_to:
                            token = t.token

                    # si no hay token vigente, crea uno
                    if not token:
                        token = _create_or_rotate_token(db, p.id)

                qr_url = f"{settings.public_base_url.rstrip('/')}/q/{token}"
                png_bytes = _make_qr_png(qr_url)

        st.download_button(
            label="Descargar PNG QR",
            data=png_bytes,
            file_name=f"QR_{action_code}.png",
            mime="image/png",
        )

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

                        from app.main import _create_or_rotate_token
                        _create_or_rotate_token(db, p.id)

                st.success("Acción aplicada correctamente.")

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
            with get_db() as db:
                from app.utils import next_passenger_code
                from app.main import _create_or_rotate_token

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

                passenger_id = str(p.id)
                passenger_code = p.code

                _create_or_rotate_token(db, p.id)

            st.success(f"Pasajero creado: {passenger_code}")
            st.info(f"Para reenviar QR: usa /api/passengers/{passenger_id}/qr/regen (descarga PNG).")

with tabs[2]:
    st.subheader("Planes mensuales")
    month = st.date_input(
        "Mes (usar 1er día del mes)",
        value=date(date.today().year, date.today().month, 1),
        key="subs_month",
    )

    with get_db() as db:
        subs = db.execute(
            select(Subscription, Passenger)
            .join(Passenger, Passenger.id == Subscription.passenger_id)
            .where(Subscription.month == month)
            .order_by(Passenger.code)
        ).all()

        subs_rows = []
        for s, p in subs:
            used_total = (s.rides_used_ida or 0) + (s.rides_used_vuelta or 0)
            remaining = max(0, (s.rides_included or 0) - used_total)

            subs_rows.append({
                "passenger_code": p.code,
                "full_name": p.full_name,
                "plan_type": s.plan_type.value if s.plan_type else None,
                "payment_status": s.payment_status.value if s.payment_status else None,
                "rides_included": s.rides_included,
                "rides_used_ida": s.rides_used_ida,
                "rides_used_vuelta": s.rides_used_vuelta,
                "rides_used_total": used_total,
                "rides_remaining": remaining,
            })

    if subs_rows:
        dfs = pd.DataFrame(subs_rows)
        st.dataframe(dfs, use_container_width=True)
        download_df(dfs, f"subs_{month.isoformat()}.csv")
    else:
        st.info("Sin planes para este mes.")

    st.markdown("---")
    st.markdown("### Activar / Actualizar plan (manual por pago)")

    with st.form("activate_sub"):
        passenger_code = st.text_input("Código pasajero (ej: ECO0001)").strip().upper()

        plan_type = st.selectbox(
            "Tipo de plan",
            [
                PlanType.VIAJES_10.value,
                PlanType.VIAJES_20.value,
                PlanType.VIAJES_30.value,
                PlanType.VIAJES_40.value,
            ],
        )

        pay_status = st.selectbox("Estado de pago", [ps.value for ps in PaymentStatus], index=0)
        reset_usage = st.checkbox("Resetear uso del mes (dejar usados en 0)", value=False)
        notes = st.text_area("Notas (opcional)")
        ok = st.form_submit_button("Guardar")

    if ok:
        PLAN_RIDES = {
            "VIAJES_10": 10,
            "VIAJES_20": 20,
            "VIAJES_30": 30,
            "VIAJES_40": 40,
        }
        rides_included = PLAN_RIDES[plan_type]

        from app.main import _create_or_rotate_token
        from app.utils import now_local

        with get_db() as db:
            p = db.execute(select(Passenger).where(Passenger.code == passenger_code)).scalar_one_or_none()
            if not p:
                st.error("No existe pasajero")
            else:
                sub = db.execute(
                    select(Subscription).where(
                        and_(Subscription.passenger_id == p.id, Subscription.month == month)
                    )
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

                # QR mensual: solo se rota cuando tú guardas el plan (seguridad)
                _create_or_rotate_token(db, p.id)

                st.success("Plan guardado y QR rotado.")

with tabs[3]:
    st.subheader("Pase diario")
    d = st.date_input("Fecha", value=date.today(), key="dp_date")
    trip = st.selectbox("Tipo de viaje", [t.value for t in TripType])

with get_db() as db:
    rows = db.execute(
        select(DailyPass, Passenger)
        .join(Passenger, Passenger.id == DailyPass.passenger_id)
        .where(and_(DailyPass.service_date==d, DailyPass.trip_type==TripType(trip)))
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
    st.markdown("### Crear solicitud")
    with st.form("dp_create"):
        passenger_code = st.text_input("Código pasajero", key="dp_code")
        pay_status = st.selectbox("Estado de pago", [ps.value for ps in PaymentStatus], key="dp_pay")
        res_status = st.selectbox("Estado reserva", [rs.value for rs in ReservationStatus], key="dp_res")
        ok = st.form_submit_button("Crear")

    if ok:
        with get_db() as db:
            p = db.execute(select(Passenger).where(Passenger.code == passenger_code.strip())).scalar_one_or_none()
            if not p:
                st.error("No existe pasajero")
            else:
                dp = DailyPass(
                    passenger_id=p.id,
                    service_date=d,
                    trip_type=TripType(trip),
                    payment_status=PaymentStatus(pay_status),
                    reservation_status=ReservationStatus(res_status),
                )
                db.add(dp)
                st.success("Solicitud creada")

st.markdown("---")
st.caption("Config: Render + Postgres recomendado. TZ y ventanas horarias desde variables de entorno.")
