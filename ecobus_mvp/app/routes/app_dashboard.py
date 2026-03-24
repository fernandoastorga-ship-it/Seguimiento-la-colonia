from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.app_service import build_app_dashboard
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/dashboard", tags=["App Dashboard"])


def get_current_passenger(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")

    token = authorization.split(" ")[1]

    passenger = get_passenger_from_token(db, token)

    if not passenger:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    return passenger


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    passenger = Depends(get_current_passenger),
):
    dashboard = build_app_dashboard(
        db=db,
        passenger_id=passenger.id,
        today=date.today(),
    )

    if not dashboard:
        raise HTTPException(404, "Pasajero no encontrado")

    return dashboard
