from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.schemas import OtpRequestIn, OtpRequestOut, OtpVerifyIn, OtpVerifyOut, AuthMeOut
from app.services.otp_service import create_otp, verify_otp, detect_channel, mask_identifier
from app.services.auth_service import create_session, get_passenger_from_token, revoke_session


router = APIRouter(prefix="/app/auth", tags=["App Auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "", 1).strip()


@router.get("/health")
def auth_health():
    return {"ok": True, "module": "auth"}


@router.post("/request-otp", response_model=OtpRequestOut)
def request_otp(payload: OtpRequestIn, db: Session = Depends(get_db)):
    identifier = payload.identifier.strip()
    channel = detect_channel(identifier)

    code, _, expires_seconds = create_otp(db, identifier)

    # En esta etapa inicial lo devolvemos para pruebas.
    # En producción esto debe enviarse por email/SMS y NO devolverse.
    print(f"[OTP DEBUG] identifier={identifier} code={code}")

    return OtpRequestOut(
        ok=True,
        channel=channel,
        masked_destination=mask_identifier(identifier, channel),
        expires_in_seconds=expires_seconds,
    )


@router.post("/verify-otp", response_model=OtpVerifyOut)
def verify_otp_route(
    payload: OtpVerifyIn,
    request: Request,
    db: Session = Depends(get_db),
):
    passenger = verify_otp(db, payload.identifier.strip(), payload.code.strip())

    if not passenger:
        raise HTTPException(status_code=401, detail="Código inválido o expirado")

    if not passenger.app_enabled:
        raise HTTPException(status_code=403, detail="Acceso app deshabilitado para este usuario")

    device_info = request.headers.get("user-agent")
    token, expires_seconds = create_session(db, passenger, device_info=device_info)

    passenger_out = AuthMeOut(
        ok=True,
        passenger_id=str(passenger.id),
        full_name=passenger.full_name,
        email=passenger.email,
        phone=passenger.phone,
        app_enabled=passenger.app_enabled,
    )

    return OtpVerifyOut(
        ok=True,
        access_token=token,
        expires_in_seconds=expires_seconds,
        passenger=passenger_out,
    )

@router.get("/me", response_model=AuthMeOut)
def me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token no enviado")

    passenger = get_passenger_from_token(db, token)
    if not passenger:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    return AuthMeOut(
        ok=True,
        passenger_id=str(passenger.id),
        full_name=passenger.full_name,
        email=passenger.email,
        phone=passenger.phone,
        app_enabled=passenger.app_enabled,
    )


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token no enviado")

    ok = revoke_session(db, token)
    return {"ok": ok}
