"""
Cliente de MinIO compartido (S3-compatible).
Usa boto3 porque es el cliente más maduro y compatible.
"""
from functools import lru_cache
from datetime import timedelta
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


@lru_cache(maxsize=1)
def get_storage_client():
    """
    Retorna un cliente boto3 S3 configurado para MinIO.
    Cacheado: una sola instancia por proceso.
    """
    if not settings.minio_endpoint or not settings.minio_access_key:
        raise RuntimeError(
            "MINIO_ENDPOINT y MINIO_ACCESS_KEY deben estar configuradas en .env"
        )

    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name=settings.minio_region,
        # signature_version='s3v4' es lo que MinIO espera
        config=Config(signature_version="s3v4"),
    )


def upload_file(
    local_path: str | Path,
    bucket: str,
    object_key: str,
    content_type: str | None = None,
) -> bool:
    """
    Sube un archivo local a MinIO.

    Args:
        local_path: Ruta del archivo local.
        bucket: Nombre del bucket destino.
        object_key: Path/nombre del objeto dentro del bucket.
        content_type: MIME type opcional (ej. "video/mp4").

    Returns:
        True si tuvo éxito, False si falló.
    """
    client = get_storage_client()
    try:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        client.upload_file(
            Filename=str(local_path),
            Bucket=bucket,
            Key=object_key,
            ExtraArgs=extra_args if extra_args else None,
        )
        return True
    except ClientError as e:
        print(f"❌ Error subiendo archivo a MinIO: {e}")
        return False


def upload_bytes(
    data: bytes,
    bucket: str,
    object_key: str,
    content_type: str | None = None,
) -> bool:
    """Sube datos en memoria directamente a MinIO."""
    client = get_storage_client()
    try:
        kwargs = {
            "Bucket": bucket,
            "Key": object_key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type

        client.put_object(**kwargs)
        return True
    except ClientError as e:
        print(f"❌ Error subiendo bytes a MinIO: {e}")
        return False


def get_presigned_url(
    bucket: str,
    object_key: str,
    expires_in_seconds: int = 3600,
) -> str | None:
    """
    Genera una URL firmada temporal para descargar un objeto.

    Args:
        bucket: Bucket donde está el objeto.
        object_key: Path del objeto.
        expires_in_seconds: Cuánto dura la URL (default 1 hora).

    Returns:
        URL firmada o None si falló.
    """
    client = get_storage_client()
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=expires_in_seconds,
        )
        return url
    except ClientError as e:
        print(f"❌ Error generando URL firmada: {e}")
        return None


def health_check() -> dict:
    """Verifica conectividad con MinIO listando buckets."""
    try:
        client = get_storage_client()
        response = client.list_buckets()
        buckets = [b["Name"] for b in response.get("Buckets", [])]
        return {
            "status": "connected",
            "buckets": buckets,
            "endpoint": settings.minio_endpoint,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }

