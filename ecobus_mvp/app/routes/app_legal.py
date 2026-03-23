from fastapi import APIRouter

router = APIRouter(prefix="/app/legal", tags=["App Legal"])


@router.get("/health")
def legal_health():
    return {
        "ok": True,
        "module": "app_legal",
        "message": "Módulo legal listo para desarrollar",
    }
