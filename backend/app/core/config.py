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

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = "" 
    # MinIO
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_use_ssl: bool = False
    minio_bucket_videos: str = "aironvision-videos"
    minio_bucket_data: str = "aironvision-data"
    minio_region: str = "us-east-1"

    # CV
    cv_model_path: str = "app/modules/cv_feedback/models/pose_landmarker_heavy.task"


settings = Settings()

