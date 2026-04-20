from __future__ import annotations

from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import desc

from app.config import settings
from app.db import get_db
from app.models import (
    Passenger,
    PickupPoint,
    Service,
    ServiceCode,
    VehicleLocation,
)
from app.services.auth_service import get_passenger_from_token
from app.utils import is_tracking_window_now, now_local


router = APIRouter(tags=["Bus Tracking"])
security = HTTPBearer()


class DriverLocationIn(BaseModel):
    service_code: str
    lat: float
    lng: float
    driver_pin: str
    source: str | None = None


def _pickup_coords(pickup_point: PickupPoint | None) -> tuple[float, float] | None:
    if pickup_point == PickupPoint.LA_COLONIA:
        if settings.pickup_la_colonia_lat is None or settings.pickup_la_colonia_lng is None:
            return None
        return (settings.pickup_la_colonia_lat, settings.pickup_la_colonia_lng)

    if pickup_point == PickupPoint.CRUCE_MALLOCO:
        if settings.pickup_cruce_malloco_lat is None or settings.pickup_cruce_malloco_lng is None:
            return None
        return (settings.pickup_cruce_malloco_lat, settings.pickup_cruce_malloco_lng)

    if pickup_point == PickupPoint.LA_MONEDA:
        if settings.pickup_la_moneda_lat is None or settings.pickup_la_moneda_lng is None:
            return None
        return (settings.pickup_la_moneda_lat, settings.pickup_la_moneda_lng)

    return None


def _current_operational_pickup() -> PickupPoint | None:
    now_t = now_local().timetz().replace(tzinfo=None)

    if (
        settings.tracking_window_morning_start
        <= now_t
        <= settings.tracking_window_morning_end
    ):
        return PickupPoint.LA_COLONIA

    if (
        settings.tracking_window_evening_start
        <= now_t
        <= settings.tracking_window_evening_end
    ):
        return PickupPoint.LA_MONEDA

    return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0

    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return r * c


def _latest_vehicle_location(db, service_id: int) -> VehicleLocation | None:
    return (
        db.query(VehicleLocation)
        .filter(
            VehicleLocation.service_id == service_id,
            VehicleLocation.is_active == True,
        )
        .order_by(desc(VehicleLocation.recorded_at), desc(VehicleLocation.id))
        .first()
    )


def _tracking_windows_label() -> list[str]:
    return [
        f"{settings.tracking_window_morning_start.strftime('%H:%M')} - {settings.tracking_window_morning_end.strftime('%H:%M')}",
        f"{settings.tracking_window_evening_start.strftime('%H:%M')} - {settings.tracking_window_evening_end.strftime('%H:%M')}",
    ]


@router.post("/api/vehicle-locations")
def post_vehicle_location(payload: DriverLocationIn):
    if payload.driver_pin != settings.driver_app_pin:
        raise HTTPException(status_code=403, detail="PIN de conductor inválido")

    try:
        service_code = ServiceCode(payload.service_code)
    except ValueError:
        raise HTTPException(status_code=400, detail="service_code inválido")

    with get_db() as db:
        service = (
            db.query(Service)
            .filter(Service.code == service_code)
            .first()
        )

        if not service:
            raise HTTPException(status_code=404, detail="Servicio no encontrado")

        loc = VehicleLocation(
            service_id=service.id,
            lat=payload.lat,
            lng=payload.lng,
            source=payload.source or "driver_app",
            recorded_at=now_local().replace(tzinfo=None),
            is_active=True,
        )
        db.add(loc)
        db.flush()

        return {
            "ok": True,
            "service_code": service_code.value,
            "recorded_at": loc.recorded_at,
        }


@router.get("/app/bus-tracking/", dependencies=[Depends(security)])
def get_bus_tracking(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if not settings.tracking_enabled:
        return {
            "available": False,
            "reason": "disabled",
            "message": "Seguimiento no disponible en este momento.",
            "windows": _tracking_windows_label(),
        }

    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        if not is_tracking_window_now():
            return {
                "available": False,
                "reason": "outside_window",
                "message": "El seguimiento del bus solo está disponible en las ventanas horarias configuradas.",
                "windows": _tracking_windows_label(),
                "server_time": now_local().isoformat(),
            }

        if not passenger.service_id:
            return {
                "available": False,
                "reason": "no_service",
                "message": "Tu usuario no tiene un servicio asignado.",
                "windows": _tracking_windows_label(),
            }

        target_pickup = _current_operational_pickup()
        if not target_pickup:
            return {
                "available": False,
                "reason": "outside_window",
                "message": "El seguimiento del bus solo está disponible en las ventanas horarias configuradas.",
                "windows": _tracking_windows_label(),
                "server_time": now_local().isoformat(),
            }

        pickup_coords = _pickup_coords(target_pickup)
        if not pickup_coords:
            return {
                "available": False,
                "reason": "pickup_not_configured",
                "message": "El punto operativo del seguimiento no tiene coordenadas configuradas.",
                "windows": _tracking_windows_label(),
            }

        latest = _latest_vehicle_location(db, passenger.service_id)
        if not latest:
            return {
                "available": False,
                "reason": "no_live_location",
                "message": "Aún no hay ubicación disponible del bus.",
                "windows": _tracking_windows_label(),
            }

        now_naive = now_local().replace(tzinfo=None)
        age_seconds = int((now_naive - latest.recorded_at).total_seconds())

        if age_seconds > settings.tracking_location_stale_seconds:
            return {
                "available": False,
                "reason": "stale_location",
                "message": "La ubicación del bus está desactualizada.",
                "windows": _tracking_windows_label(),
                "last_update_seconds": age_seconds,
            }

        pickup_lat, pickup_lng = pickup_coords
        distance_km = _haversine_km(latest.lat, latest.lng, pickup_lat, pickup_lng)

        avg_speed = settings.tracking_avg_speed_kmh if settings.tracking_avg_speed_kmh > 0 else 22
        eta_minutes = max(1, round((distance_km / avg_speed) * 60))

        if eta_minutes <= 2:
            status = "llegando"
        elif eta_minutes <= 7:
            status = "cerca"
        else:
            status = "en_camino"

        return {
            "available": True,
            "status": status,
            "eta_minutes": eta_minutes,
            "distance_km": round(distance_km, 2),
            "refresh_seconds": settings.tracking_poll_seconds,
            "windows": _tracking_windows_label(),
            "last_update_seconds": age_seconds,
            "bus": {
                "lat": latest.lat,
                "lng": latest.lng,
                "recorded_at": latest.recorded_at,
            },
            "pickup": {
                "name": target_pickup.value,
                "lat": pickup_lat,
                "lng": pickup_lng,
            },
        }
