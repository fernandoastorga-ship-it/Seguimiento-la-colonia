import os
from dataclasses import dataclass
from datetime import time


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default


def _parse_hhmm(v: str) -> time:
    hh, mm = v.strip().split(":")
    return time(hour=int(hh), minute=int(mm))


@dataclass(frozen=True)
class Settings:
    tz: str = _env("TZ", "America/Santiago")

    time_window_ida_start: time = _parse_hhmm(_env("TIME_WINDOW_IDA_START", "05:30"))
    time_window_ida_end: time = _parse_hhmm(_env("TIME_WINDOW_IDA_END", "06:10"))
    time_window_vuelta_start: time = _parse_hhmm(_env("TIME_WINDOW_VUELTA_START", "18:00"))
    time_window_vuelta_end: time = _parse_hhmm(_env("TIME_WINDOW_VUELTA_END", "19:30"))

    duplicate_minutes: int = int(_env("DUPLICATE_MINUTES", "3"))
    bus_capacity: int = int(_env("BUS_CAPACITY", "45"))
    monthly_reserved: int = int(_env("MONTHLY_RESERVED", "35"))
    daily_reserved: int = int(_env("DAILY_RESERVED", "10"))

    scanner_pin: str = _env("SCANNER_PIN", "1234")

    database_url: str = _env("DATABASE_URL", "sqlite:///./data.db")

    # Base URL used inside QR content. In Render, set to your public URL.
    public_base_url: str = _env("PUBLIC_BASE_URL", "http://localhost:8000")


settings = Settings()
