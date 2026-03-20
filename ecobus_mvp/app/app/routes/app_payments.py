from fastapi import APIRouter

router = APIRouter(prefix="/app/payments", tags=["App Payments"])


@router.get("/health")
def payments_health():
    return {
        "ok": True,
        "module": "app_payments",
        "message": "Módulo de pagos listo para desarrollar",
    }
