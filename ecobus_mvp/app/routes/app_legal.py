from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_db
from app.services.auth_service import get_passenger_from_token


router = APIRouter(prefix="/app/legal", tags=["App Legal"])

security = HTTPBearer()

CURRENT_TERMS_VERSION = "v1.0"


TERMS_TITLE = "Términos y Condiciones de Uso - Ecobus"
TERMS_TEXT = """
Bienvenido a la app de pasajeros de Ecobus.

Al utilizar esta aplicación, el pasajero acepta las condiciones de uso del sistema de validación,
reserva y control de viajes implementado por Ecobus/Ecovan.

1. La app permite visualizar información personal vinculada al servicio contratado, incluyendo
   estado del plan, viajes disponibles, historial de validaciones y códigos QR de uso operativo.

2. El QR mensual es personal e intransferible, y su uso indebido puede provocar bloqueo o revisión
   del servicio.

3. Los QR de pase diario, cuando existan, podrán ser de un solo uso y estarán sujetos a validación
   de pago, reserva y fecha de servicio.

4. Ecobus podrá actualizar las condiciones de uso cuando sea necesario para mejorar la operación,
   seguridad o cumplimiento del servicio.

5. El pasajero es responsable de mantener actualizados sus datos de contacto y de resguardar
   el acceso a su cuenta.

6. La información mostrada en la app tiene carácter operativo y podrá depender de procesos de
   validación interna, pagos confirmados y disponibilidad del servicio.

7. El uso de esta app implica aceptación de la versión vigente de estos términos.
""".strip()


def _get_authenticated_passenger(credentials: HTTPAuthorizationCredentials):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return passenger


@router.get("/", dependencies=[Depends(security)])
def get_legal_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        accepted_version = passenger.accepted_terms_version
        accepted_at = passenger.accepted_terms_at

        return {
            "document": {
                "type": "terms_and_conditions",
                "title": TERMS_TITLE,
                "version": CURRENT_TERMS_VERSION,
                "content": TERMS_TEXT,
            },
            "acceptance": {
                "accepted": accepted_version == CURRENT_TERMS_VERSION,
                "accepted_terms_version": accepted_version,
                "accepted_terms_at": accepted_at,
                "current_terms_version": CURRENT_TERMS_VERSION,
                "needs_acceptance": accepted_version != CURRENT_TERMS_VERSION,
            },
        }


@router.post("/accept", dependencies=[Depends(security)])
def accept_current_terms(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    with get_db() as db:
        passenger = get_passenger_from_token(db, token)
        if not passenger:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")

        now = datetime.utcnow()

        passenger.accepted_terms_version = CURRENT_TERMS_VERSION
        passenger.accepted_terms_at = now

        db.add(passenger)

        return {
            "ok": True,
            "message": "Términos aceptados correctamente",
            "accepted_terms_version": passenger.accepted_terms_version,
            "accepted_terms_at": passenger.accepted_terms_at,
        }
