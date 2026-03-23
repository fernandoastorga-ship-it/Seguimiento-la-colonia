from fastapi import APIRouter

router = APIRouter(prefix="/app/auth", tags=["App Auth"])


@router.get("/health")
def auth_health():
    return {
        "ok": True,
        "module": "app_auth",
        "message": "Módulo de autenticación listo para desarrollar",
    }
