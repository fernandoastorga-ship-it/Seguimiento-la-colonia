from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.app_service import build_app_dashboard
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/dashboard", tags=["App Dashboard"])

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_passenger(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token requerido")

    token = credentials.credentials
    passenger = get_passenger_from_token(db, token)

    if not passenger:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    return passenger


@router.get("/")
def get_dashboard(
    passenger = Depends(get_current_passenger),
    db: Session = Depends(get_db),
):
    dashboard = build_app_dashboard(
        db=db,
        passenger_id=passenger.id,
        today=date.today(),
    )

    if not dashboard:
        raise HTTPException(status_code=404, detail="Pasajero no encontrado")

    return dashboard
