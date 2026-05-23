"""
Persistence Service para cv_feedback.

Guarda los resultados de análisis en Supabase (Postgres).
- Tabla squat_analyses: una fila por análisis (resumen)
- Tabla squat_reps: una fila por repetición (detalle)

Filosofía:
- Recibe AnalysisResult + URLs + user_id
- Hace inserts atómicos (si falla algo, ambas tablas hacen rollback)
- Retorna el analysis_id (UUID) generado por Postgres
- No conoce de MinIO ni de FastAPI
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.supabase_client import get_service_client
from app.modules.cv_feedback.analyzers.base import AnalysisResult
from app.modules.cv_feedback.schemas import AnalysisStatus


class PersistenceService:
    """
    Persiste análisis de ejercicios en Supabase.

    Por ahora solo maneja sentadillas (tablas squat_analyses + squat_reps).
    Cuando agreguemos más ejercicios, generalizaremos.
    """

    def __init__(self):
        self.client = get_service_client()

    # -------------------------------------------------
    # Persistir análisis completo
    # -------------------------------------------------

    def save_squat_analysis(
        self,
        user_id: UUID | str,
        result: AnalysisResult,
        original_video_url: str | None = None,
        annotated_video_url: str | None = None,
    ) -> UUID:
        """
        Guarda un análisis completo de sentadilla en Supabase.

        Args:
            user_id: UUID del usuario dueño del análisis.
            result: AnalysisResult del SquatAnalyzer.
            original_video_url: Path/key del video original en MinIO (opcional).
            annotated_video_url: Path/key del video anotado en MinIO (opcional).

        Returns:
            analysis_id (UUID) generado por Postgres.

        Raises:
            RuntimeError si falla cualquier inserción.
        """
        # 1. Construir payload del análisis principal
        analysis_payload = self._build_analysis_payload(
            user_id=user_id,
            result=result,
            original_video_url=original_video_url,
            annotated_video_url=annotated_video_url,
        )

        # 2. Insertar en squat_analyses y obtener el ID generado
        analysis_id = self._insert_analysis(analysis_payload)

        # 3. Insertar todas las reps
        if result.reps:
            self._insert_reps(analysis_id, result.reps)

        return analysis_id

    # -------------------------------------------------
    # Construcción de payloads
    # -------------------------------------------------

    @staticmethod
    def _build_analysis_payload(
        user_id: UUID | str,
        result: AnalysisResult,
        original_video_url: str | None,
        annotated_video_url: str | None,
    ) -> dict[str, Any]:
        """Mapea AnalysisResult al schema de la tabla squat_analyses."""
        meta = result.video_metadata
        summary = result.summary

        return {
            "user_id": str(user_id),

            # Metadata del video
            "video_filename": meta.filename,
            "video_size_bytes": meta.size_bytes,
            "video_duration_sec": float(meta.duration_sec),
            "video_fps": float(meta.fps),
            "video_width": meta.width,
            "video_height": meta.height,

            # URLs en MinIO
            "original_video_url": original_video_url,
            "annotated_video_url": annotated_video_url,

            # Resumen
            "total_reps": summary.total_reps,
            "avg_depth_angle": float(summary.mean_depth_angle),
            "min_depth_angle": float(summary.min_depth_angle),
            "max_depth_angle": float(summary.max_depth_angle),
            "depth_consistency_std": float(summary.depth_consistency_std),
            "avg_rep_interval_sec": float(summary.avg_rep_interval_sec),
            "detection_quality": float(summary.detection_quality),

            # Estado
            "status": AnalysisStatus.COMPLETED.value,
            "processed_at": datetime.now(timezone.utc).isoformat(),

            # NOTA: full_analysis_json lo dejamos vacío por ahora.
            # En una iteración futura podemos guardar aquí el DataFrame
            # completo serializado (para análisis posteriores).
        }

    # -------------------------------------------------
    # Inserts en Supabase
    # -------------------------------------------------

    def _insert_analysis(self, payload: dict[str, Any]) -> UUID:
        """Inserta una fila en squat_analyses y retorna el UUID generado."""
        response = (
            self.client.table("squat_analyses")
            .insert(payload)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise RuntimeError(
                f"Falló insert en squat_analyses: respuesta vacía. {response}"
            )

        analysis_id_str = response.data[0]["id"]
        return UUID(analysis_id_str)

    def _insert_reps(self, analysis_id: UUID, reps: list) -> None:
        """Inserta todas las reps en squat_reps (bulk insert)."""
        rows = [
            {
                "analysis_id": str(analysis_id),
                "rep_number": rep.rep_number,
                "timestamp_sec": float(rep.timestamp_sec),
                "min_knee_angle": float(rep.min_knee_angle),
                "depth_category": rep.depth_category.value,
            }
            for rep in reps
        ]

        response = (
            self.client.table("squat_reps")
            .insert(rows)
            .execute()
        )

        if not response.data or len(response.data) != len(rows):
            raise RuntimeError(
                f"Falló insert de reps. Esperadas: {len(rows)}, "
                f"insertadas: {len(response.data) if response.data else 0}"
            )

    # -------------------------------------------------
    # Lecturas (para futuro: ver historial del usuario)
    # -------------------------------------------------

    def get_analysis_by_id(self, analysis_id: UUID | str) -> dict | None:
        """Obtiene un análisis específico por su ID."""
        response = (
            self.client.table("squat_analyses")
            .select("*")
            .eq("id", str(analysis_id))
            .single()
            .execute()
        )
        return response.data if response.data else None

    def get_user_analyses(
        self, user_id: UUID | str, limit: int = 20
    ) -> list[dict]:
        """Lista los últimos N análisis de un usuario."""
        response = (
            self.client.table("squat_analyses")
            .select("*")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response.data else []
