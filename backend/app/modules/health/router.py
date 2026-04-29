"""
Router del módulo health.
Endpoints para verificar el estado del sistema.
"""
from fastapi import APIRouter

from app.core.config import settings

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
