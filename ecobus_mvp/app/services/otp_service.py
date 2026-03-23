import hashlib
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import OtpCode, Passenger


OTP_EXP_MINUTES = 10


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def detect_channel(identifier: str) -> str:
    identifier = identifier.strip()
    if "@" in identifier:
        return "email"
    return "phone"


def mask_identifier(identifier: str, channel: str) -> str:
    if channel == "email":
        parts = identifier.split("@")
        if len(parts) != 2:
            return identifier
        name, domain = parts
        if len(name) <= 2:
            masked_name = name[0] + "*"
        else:
            masked_name = name[:2] + "*" * max(1, len(name) - 2)
        return f"{masked_name}@{domain}"

    if len(identifier) <= 4:
        return "*" * len(identifier)
    return "*" * (len(identifier) - 4) + identifier[-4:]

def normalize_identifier(identifier: str) -> str:
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier.lower()
    return identifier


def find_passenger_by_identifier(db: Session, identifier: str) -> Passenger | None:
    identifier = normalize_identifier(identifier)
    channel = detect_channel(identifier)

    if channel == "email":
        return (
            db.query(Passenger)
            .filter(Passenger.email.ilike(identifier), Passenger.is_deleted == False)
            .first()
        )

    return (
        db.query(Passenger)
        .filter(Passenger.phone == identifier, Passenger.is_deleted == False)
        .first()
    )


def create_otp(db: Session, identifier: str) -> tuple[str, str, int]:
    identifier = normalize_identifier(identifier)
    channel = detect_channel(identifier)
    code = generate_otp_code()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXP_MINUTES)

    passenger = find_passenger_by_identifier(db, identifier)

    otp = OtpCode(
        passenger_id=passenger.id if passenger else None,
        identifier=identifier,
        channel=channel,
        code_hash=_hash_code(code),
        expires_at=expires_at,
        attempts=0,
    )
    db.add(otp)
    db.commit()

    return code, channel, OTP_EXP_MINUTES * 60


def verify_otp(db: Session, identifier: str, code: str) -> Passenger | None:
    identifier = normalize_identifier(identifier)

    otp = (
        db.query(OtpCode)
        .filter(
            OtpCode.identifier == identifier,
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.created_at.desc())
        .first()
    )

    if not otp:
        return None

    if otp.expires_at < datetime.utcnow():
        return None

    otp.attempts += 1

    if otp.code_hash != _hash_code(code):
        db.commit()
        return None

    otp.consumed_at = datetime.utcnow()

    passenger = find_passenger_by_identifier(db, identifier)
    if passenger:
        if otp.channel == "email":
            passenger.email_verified_at = datetime.utcnow()
        elif otp.channel == "phone":
            passenger.phone_verified_at = datetime.utcnow()

    db.commit()
    return passenger
