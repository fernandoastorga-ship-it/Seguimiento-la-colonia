from fastapi import APIRouter

router = APIRouter(prefix="/app/qr", tags=["App QR"])


@router.get("/health")
def qr_health():
    return {
        "ok": True,
        "module": "app_qr",
        "message": "Módulo QR listo para desarrollar",
    }
