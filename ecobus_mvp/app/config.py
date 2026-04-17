import os
from dataclasses import dataclass
from datetime import time
from typing import Optional


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default


def _parse_optional_float(v: str) -> Optional[float]:
    raw = v.strip()
    if raw == "":
        return None
    return float(raw)


@dataclass(frozen=True)
class Settings:
    tz: str = _env("TZ", "America/Santiago")

    disable_time_window: bool = _env("DISABLE_TIME_WINDOW", "false").lower() in ("1", "true", "yes", "y", "on")

    time_window_ida_start: time = _parse_hhmm(_env("TIME_WINDOW_IDA_START", "00:00"))
    time_window_ida_end: time = _parse_hhmm(_env("TIME_WINDOW_IDA_END", "23:59"))
    time_window_vuelta_start: time = _parse_hhmm(_env("TIME_WINDOW_VUELTA_START", "00:00"))
    time_window_vuelta_end: time = _parse_hhmm(_env("TIME_WINDOW_VUELTA_END", "23:59"))

    duplicate_minutes: int = int(_env("DUPLICATE_MINUTES", "3"))
    bus_capacity: int = int(_env("BUS_CAPACITY", "45"))
    monthly_reserved: int = int(_env("MONTHLY_RESERVED", "35"))
    daily_reserved: int = int(_env("DAILY_RESERVED", "10"))

    scanner_pin: str = _env("SCANNER_PIN", "1234")

    database_url: str = _env("DATABASE_URL", "sqlite:///./data.db")

    # Base URL used inside QR content. In Render, set to your public URL.
    public_base_url: str = _env("PUBLIC_BASE_URL", "http://localhost:8000")

    # -------------------------
    # Tracking conductor / pasajero
    # -------------------------
    tracking_enabled: bool = _env("TRACKING_ENABLED", "true").lower() in ("1", "true", "yes", "y", "on")
    driver_app_pin: str = _env("DRIVER_APP_PIN", "5678")

    tracking_window_morning_start: time = _parse_hhmm(_env("TRACKING_WINDOW_MORNING_START", "05:30"))
    tracking_window_morning_end: time = _parse_hhmm(_env("TRACKING_WINDOW_MORNING_END", "07:00"))
    tracking_window_evening_start: time = _parse_hhmm(_env("TRACKING_WINDOW_EVENING_START", "17:00"))
    tracking_window_evening_end: time = _parse_hhmm(_env("TRACKING_WINDOW_EVENING_END", "19:00"))

    tracking_location_stale_seconds: int = int(_env("TRACKING_LOCATION_STALE_SECONDS", "90"))
    tracking_poll_seconds: int = int(_env("TRACKING_POLL_SECONDS", "10"))
    tracking_avg_speed_kmh: float = float(_env("TRACKING_AVG_SPEED_KMH", "22"))

    pickup_la_colonia_lat: Optional[float] = _parse_optional_float(_env("PICKUP_LA_COLONIA_LAT", ""))
    pickup_la_colonia_lng: Optional[float] = _parse_optional_float(_env("PICKUP_LA_COLONIA_LNG", ""))
    pickup_cruce_malloco_lat: Optional[float] = _parse_optional_float(_env("PICKUP_CRUCE_MALLOCO_LAT", ""))
    pickup_cruce_malloco_lng: Optional[float] = _parse_optional_float(_env("PICKUP_CRUCE_MALLOCO_LNG", ""))
    pickup_la_moneda_lat: Optional[float] = _parse_optional_float(_env("PICKUP_LA_MONEDA_LAT", ""))
    pickup_la_moneda_lng: Optional[float] = _parse_optional_float(_env("PICKUP_LA_MONEDA_LNG", ""))


settings = Settings()
