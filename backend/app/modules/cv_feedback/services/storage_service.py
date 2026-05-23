"""
Storage Service para cv_feedback.

Encapsula la lógica de almacenamiento de videos y datos del análisis.
Usa internamente el cliente de MinIO (app.core.storage_client).

Convención de paths en buckets:
- aironvision-videos/{user_id}/{analysis_id}/original.mp4
- aironvision-videos/{user_id}/{analysis_id}/annotated.mp4
- aironvision-data/{user_id}/{analysis_id}/keypoints.json
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.storage_client import (
    get_presigned_url,
    upload_bytes,
    upload_file,
)


class StorageService:
    """
    Maneja el almacenamiento de assets de análisis en MinIO.

    Convención: cada análisis tiene una "carpeta" identificada por
    {user_id}/{analysis_id}/ en cada bucket.
    """

    def __init__(self):
        self.videos_bucket = settings.minio_bucket_videos
        self.data_bucket = settings.minio_bucket_data

    # -------------------------------------------------
    # Paths convencionales
    # -------------------------------------------------

    @staticmethod
    def _build_object_key(user_id: UUID | str, analysis_id: UUID | str, filename: str) -> str:
        """Construye el path estándar dentro de un bucket."""
        return f"{user_id}/{analysis_id}/{filename}"

    # -------------------------------------------------
    # Upload
    # -------------------------------------------------

    def upload_original_video(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        local_path: str | Path,
    ) -> str:
        """
        Sube el video original del usuario a MinIO.

        Returns:
            object_key del video subido.

        Raises:
            RuntimeError si la subida falla.
        """
        object_key = self._build_object_key(user_id, analysis_id, "original.mp4")
        success = upload_file(
            local_path=local_path,
            bucket=self.videos_bucket,
            object_key=object_key,
            content_type="video/mp4",
        )
        if not success:
            raise RuntimeError(f"Falló subir video original a MinIO: {object_key}")
        return object_key

    def upload_annotated_video(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        local_path: str | Path,
    ) -> str:
        """Sube el video anotado generado por el analyzer."""
        object_key = self._build_object_key(user_id, analysis_id, "annotated.mp4")
        success = upload_file(
            local_path=local_path,
            bucket=self.videos_bucket,
            object_key=object_key,
            content_type="video/mp4",
        )
        if not success:
            raise RuntimeError(f"Falló subir video anotado a MinIO: {object_key}")
        return object_key

    def upload_keypoints_json(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        json_data: bytes,
    ) -> str:
        """Sube el JSON con todos los keypoints del análisis (datos detallados)."""
        object_key = self._build_object_key(user_id, analysis_id, "keypoints.json")
        success = upload_bytes(
            data=json_data,
            bucket=self.data_bucket,
            object_key=object_key,
            content_type="application/json",
        )
        if not success:
            raise RuntimeError(f"Falló subir keypoints JSON: {object_key}")
        return object_key

    # -------------------------------------------------
    # URLs firmadas (para que el cliente acceda)
    # -------------------------------------------------

    def get_annotated_video_url(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        expires_in_seconds: int = 3600,
    ) -> str | None:
        """Genera URL firmada temporal para descargar el video anotado."""
        object_key = self._build_object_key(user_id, analysis_id, "annotated.mp4")
        return get_presigned_url(
            bucket=self.videos_bucket,
            object_key=object_key,
            expires_in_seconds=expires_in_seconds,
        )

    def get_original_video_url(
        self,
        user_id: UUID | str,
        analysis_id: UUID | str,
        expires_in_seconds: int = 3600,
    ) -> str | None:
        """URL firmada para el video original."""
        object_key = self._build_object_key(user_id, analysis_id, "original.mp4")
        return get_presigned_url(
            bucket=self.videos_bucket,
            object_key=object_key,
            expires_in_seconds=expires_in_seconds,
        )
