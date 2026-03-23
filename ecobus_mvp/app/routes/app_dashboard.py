from fastapi import APIRouter

router = APIRouter(prefix="/app/dashboard", tags=["App Dashboard"])


@router.get("/")
def get_dashboard():
    return {
        "ok": True,
        "message": "Dashboard passenger app funcionando 🚀",
        "module": "app_dashboard",
    }
