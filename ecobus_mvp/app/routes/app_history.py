from fastapi import APIRouter

router = APIRouter(prefix="/app/history", tags=["App History"])


@router.get("/health")
def history_health():
    return {
        "ok": True,
        "module": "app_history",
        "message": "Módulo de historial listo para desarrollar",
    }
