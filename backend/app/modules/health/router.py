"""
Router del módulo health.
Endpoints para verificar el estado del sistema.
"""
from fastapi import APIRouter

from app.core.config import settings
from app.core.supabase_client import get_service_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> dict:
    """Endpoint básico de salud."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
    }


@router.get("/ping")
async def ping() -> dict:
    """Ping simple para verificar latencia."""
    return {"message": "pong"}


@router.get("/supabase")
async def supabase_check() -> dict:
    """
    Verifica que la conexión con Supabase funcione.
    Hace una query trivial al schema de auth.
    """
    try:
        client = get_service_client()
        # Query trivial: listar usuarios (estará vacío al inicio)
        response = client.auth.admin.list_users()
        users_count = len(response) if isinstance(response, list) else 0
        return {
            "status": "connected",
            "users_count": users_count,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
