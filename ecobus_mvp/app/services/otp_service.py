import hashlib
import os
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


def send_otp_email(to_email: str, code: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL")
    from_name = os.getenv("FROM_NAME", "Ecobus")

    missing = []
    if not smtp_host:
        missing.append("SMTP_HOST")
    if not smtp_user:
        missing.append("SMTP_USER")
    if not smtp_pass:
        missing.append("SMTP_PASS")
    if not from_email:
        missing.append("FROM_EMAIL")

    if missing:
        raise RuntimeError(f"Faltan variables SMTP: {', '.join(missing)}")

    subject = "Tu código de acceso Ecobus"
    text_body = (
        f"Tu código de acceso Ecobus es: {code}\n\n"
        f"Este código vence en {OTP_EXP_MINUTES} minutos.\n\n"
        f"Si no solicitaste este acceso, puedes ignorar este correo."
    )
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2 style="margin-bottom: 8px;">Ecobus</h2>
        <p>Tu código de acceso es:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 6px; margin: 18px 0;">
          {code}
        </div>
        <p>Este código vence en <b>{OTP_EXP_MINUTES} minutos</b>.</p>
        <p>Si no solicitaste este acceso, puedes ignorar este correo.</p>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    server = None
    try:
        print(f"[OTP EMAIL] Conectando SMTP host={smtp_host} port={smtp_port} user={smtp_user}")
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())
        print(f"[OTP EMAIL] Correo enviado correctamente a {to_email}")
    except Exception as e:
        print(f"[OTP EMAIL] ERROR enviando correo a {to_email}: {repr(e)}")
        raise
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


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

    # Envío OTP por correo si el identificador es email
    if channel == "email":
        send_otp_email(identifier, code)
    else:
        print(f"[OTP SMS] No implementado para identifier={identifier}. Código generado={code}")

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

    print(f"[VERIFY OTP] identifier_normalized={identifier}")
    print(f"[VERIFY OTP] otp_found={otp is not None}")

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
    print(f"[VERIFY OTP] passenger_found={passenger is not None}")

    if passenger:
        if otp.channel == "email":
            passenger.email_verified_at = datetime.utcnow()
        elif otp.channel == "phone":
            passenger.phone_verified_at = datetime.utcnow()

    db.commit()
    return passenger
