"""
Analysis Service - Orquestador del pipeline de análisis.

Coordina:
1. Analyzer (CV puro) - extrae datos del video
2. StorageService - sube videos a MinIO
3. PersistenceService - guarda metadata en Supabase

Es el punto de entrada que usa el router HTTP.
No expone detalles internos de los services individuales.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import settings
from app.modules.cv_feedback.analyzers.base import BaseExerciseAnalyzer
from app.modules.cv_feedback.analyzers.squat_analyzer import SquatAnalyzer
from app.modules.cv_feedback.services.persistence_service import PersistenceService
from app.modules.cv_feedback.services.storage_service import StorageService


# Mapeo de tipo de ejercicio → clase de analyzer
# Cuando agregues peso muerto o press de banca, solo agregas la entrada aquí.
ANALYZER_REGISTRY: dict[str, type[BaseExerciseAnalyzer]] = {
    "squat": SquatAnalyzer,
    # "deadlift": DeadliftAnalyzer,  # Futuro
    # "bench_press": BenchPressAnalyzer,  # Futuro
}


class AnalysisService:
    """Orquestador del pipeline completo de análisis."""

    def __init__(
        self,
        storage_service: StorageService | None = None,
        persistence_service: PersistenceService | None = None,
    ):
        """
        Permite inyectar dependencias para tests. Si no se pasan, usa defaults.
        """
        self.storage = storage_service or StorageService()
        self.persistence = persistence_service or PersistenceService()

    # -------------------------------------------------
    # Pipeline público
    # -------------------------------------------------

    def analyze_exercise(
        self,
        user_id: UUID | str,
        exercise_type: str,
        video_path: Path,
    ) -> dict:
        """
        Ejecuta el pipeline completo de análisis.

        Args:
            user_id: UUID del usuario dueño del video.
            exercise_type: 'squat' (por ahora el único soportado).
            video_path: Ruta local al video a analizar.

        Returns:
            Dict con: analysis_id, summary, reps, annotated_video_url

        Raises:
            ValueError si el ejercicio no está soportado.
            RuntimeError si algún paso del pipeline falla.
        """
        # 1. Validar ejercicio soportado
        analyzer_class = ANALYZER_REGISTRY.get(exercise_type)
        if analyzer_class is None:
            raise ValueError(
                f"Ejercicio '{exercise_type}' no soportado. "
                f"Disponibles: {list(ANALYZER_REGISTRY.keys())}"
            )

        # 2. Generar analysis_id ANTES de procesar (lo usamos en paths de MinIO)
        analysis_id = uuid4()

        # 3. Crear analyzer y procesar
        analyzer = analyzer_class(model_path=settings.cv_model_path)
        result = analyzer.analyze(video_path)

        # 4. Generar video anotado en temporal
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            annotated_path = Path(tmp.name)

        try:
            analyzer.generate_annotated_video(
                input_video_path=video_path,
                output_video_path=annotated_path,
                result=result,
            )

            # 5. Subir a MinIO
            annotated_key = self.storage.upload_annotated_video(
                user_id=user_id,
                analysis_id=analysis_id,
                local_path=annotated_path,
            )
        finally:
            if annotated_path.exists():
                annotated_path.unlink()

        # 6. Persistir en Supabase
        # Nota: el analysis_id ya lo conocemos, pero persistence genera uno
        # propio en la DB. Por ahora confiamos en el de la DB.
        # TODO: refactor para que persistence acepte un analysis_id pre-generado
        saved_id = self.persistence.save_squat_analysis(
            user_id=user_id,
            result=result,
            original_video_url=None,
            annotated_video_url=annotated_key,
        )

        # 7. Generar URL firmada para el response
        annotated_url = self.storage.get_annotated_video_url(
            user_id=user_id,
            analysis_id=analysis_id,
            expires_in_seconds=3600,
        )

        # 8. Construir response
        return {
            "analysis_id": saved_id,
            "exercise_type": result.exercise_type,
            "video_metadata": result.video_metadata,
            "summary": result.summary,
            "reps": result.reps,
            "annotated_video_url": annotated_url,
        }

    # -------------------------------------------------
    # Lecturas para historial
    # -------------------------------------------------

    def get_user_history(self, user_id: UUID | str, limit: int = 20) -> list[dict]:
        """Lista los análisis del usuario."""
        return self.persistence.get_user_analyses(user_id, limit=limit)

    def get_analysis_detail(self, analysis_id: UUID | str) -> dict | None:
        """Obtiene un análisis específico con su URL firmada fresca."""
        analysis = self.persistence.get_analysis_by_id(analysis_id)
        if not analysis:
            return None

        # Si tiene video anotado en MinIO, generar URL firmada fresca
        if analysis.get("annotated_video_url"):
            # El campo guarda el object_key, no la URL firmada
            object_key = analysis["annotated_video_url"]
            # Extraer user_id y analysis_id del object_key
            # Convención: {user_id}/{analysis_id}/annotated.mp4
            parts = object_key.split("/")
            if len(parts) >= 2:
                user_id = parts[0]
                analysis_id_in_key = parts[1]
                analysis["annotated_video_signed_url"] = self.storage.get_annotated_video_url(
                    user_id=user_id,
                    analysis_id=analysis_id_in_key,
                )

        return analysis
