from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .config import settings
from .models import Passenger


def now_local() -> datetime:
    return datetime.now(tz=ZoneInfo(settings.tz))


def today_local() -> date:
    return now_local().date()


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def end_of_month(dt: datetime) -> datetime:
    # End of current month (exclusive) as a datetime
    if dt.month == 12:
        next_month = datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
    else:
        next_month = datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)
    return next_month


def in_time_window(now_t: time, start: time, end: time) -> bool:
    # Handles windows that do not cross midnight (expected here).
    return start <= now_t <= end


def local_time_now() -> time:
    return now_local().timetz().replace(tzinfo=None)


def is_tracking_window_now() -> bool:
    now_t = local_time_now()

    morning_ok = in_time_window(
        now_t,
        settings.tracking_window_morning_start,
        settings.tracking_window_morning_end,
    )

    evening_ok = in_time_window(
        now_t,
        settings.tracking_window_evening_start,
        settings.tracking_window_evening_end,
    )

    return morning_ok or evening_ok


def generate_token() -> str:
    # URL-safe, long non-guessable token
    return secrets.token_urlsafe(32)


def next_passenger_code(db: Session) -> str:
    # ECO0001 incremental
    q = select(Passenger.code)
    codes = db.execute(q).scalars().all()
    mx = 0
    for c in codes:
        m = re.match(r"ECO(\d+)", c or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return f"ECO{mx+1:04d}"


def minutes_ago(dt: datetime, minutes: int) -> datetime:
    return dt - timedelta(minutes=minutes)
