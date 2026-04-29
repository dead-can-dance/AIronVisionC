"""
Punto de entrada de AIronVision API.
Ensambla todos los módulos en una sola aplicación FastAPI.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.health.router import router as health_router


def create_app() -> FastAPI:
    """Factory de la aplicación FastAPI."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registro de routers de módulos
    app.include_router(health_router, prefix=settings.api_v1_prefix)

    @app.get("/")
    async def root() -> dict:
        return {
            "message": "AIronVision API",
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    return app


app = create_app()
