"""
Configuración central de la aplicación.
Lee variables de entorno desde .env y las valida con Pydantic.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "AIronVision API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # CORS - dominios permitidos para conectarse al backend
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Supabase (lo llenaremos en el siguiente paso)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""


settings = Settings()
