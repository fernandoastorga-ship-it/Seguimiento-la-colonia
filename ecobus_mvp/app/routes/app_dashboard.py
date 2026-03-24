from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_db
from app.services.app_service import build_app_dashboard
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/dashboard", tags=["App Dashboard"])

security = HTTPBearer()


@router.get("/", dependencies=[Depends(security)])
def get_dashboard(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        dashboard = build_app_dashboard(
            db=db,
            passenger_id=passenger.id,
            today=date.today(),
        )

        if not dashboard:
            raise HTTPException(status_code=404, detail="Pasajero no encontrado")

        return dashboard
