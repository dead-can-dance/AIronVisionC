"""
Router HTTP del módulo cv_feedback.

Expone los endpoints de análisis de video. Toda la lógica vive en services;
este router solo:
1. Valida auth (extrae user_id del JWT)
2. Maneja el upload del archivo
3. Delega al AnalysisService
4. Convierte la respuesta a JSON
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.modules.auth.dependencies import get_current_user_id
from app.modules.cv_feedback.services.analysis_service import AnalysisService


router = APIRouter(prefix="/cv-feedback", tags=["cv-feedback"])


# Tamaño máximo de upload: 100 MB (en bytes)
MAX_UPLOAD_SIZE = 100 * 1024 * 1024

# MIME types permitidos para video
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",   # .mov
    "video/x-msvideo",   # .avi
}


def get_analysis_service() -> AnalysisService:
    """Factory para inyectar el AnalysisService en endpoints."""
    return AnalysisService()


# -------------------------------------------------
# POST /analyze-squat
# -------------------------------------------------

@router.post(
    "/analyze-squat",
    status_code=status.HTTP_200_OK,
    summary="Analiza un video de sentadilla",
    description=(
        "Sube un video, lo procesa con MediaPipe, detecta repeticiones, "
        "y devuelve métricas + URL del video anotado."
    ),
)
async def analyze_squat(
    video: UploadFile = File(..., description="Archivo de video (mp4, mov, avi)"),
    user_id: UUID = Depends(get_current_user_id),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Endpoint principal de análisis de sentadilla."""

    # 1. Validaciones de archivo
    if video.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Tipo de archivo no soportado: {video.content_type}. "
                f"Permitidos: {sorted(ALLOWED_VIDEO_TYPES)}"
            ),
        )

    # 2. Guardar el upload en archivo temporal local
    # Procesamos desde disco (MediaPipe necesita un path), no desde stream
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            temp_video_path = Path(tmp.name)

            total_size = 0
            while chunk := await video.read(1024 * 1024):  # 1 MB chunks
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Video excede el tamaño máximo de {MAX_UPLOAD_SIZE // (1024*1024)} MB",
                    )
                tmp.write(chunk)
    except HTTPException:
        if temp_video_path.exists():
            temp_video_path.unlink()
        raise
    except Exception as e:
        if temp_video_path.exists():
            temp_video_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando el video: {e}",
        )

    # 3. Procesar
    try:
        result = service.analyze_exercise(
            user_id=user_id,
            exercise_type="squat",
            video_path=temp_video_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando el video: {e}",
        )
    finally:
        if temp_video_path.exists():
            temp_video_path.unlink()

    # 4. Construir response (convertir UUIDs y Pydantic a dict)
    return {
        "analysis_id": str(result["analysis_id"]),
        "exercise_type": result["exercise_type"],
        "video_metadata": result["video_metadata"].model_dump(),
        "summary": result["summary"].model_dump(),
        "reps": [rep.model_dump() for rep in result["reps"]],
        "annotated_video_url": result["annotated_video_url"],
    }


# -------------------------------------------------
# GET /history
# -------------------------------------------------

@router.get(
    "/history",
    summary="Lista los análisis del usuario autenticado",
)
async def get_history(
    limit: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Retorna los últimos N análisis del usuario."""
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit debe estar entre 1 y 100",
        )

    history = service.get_user_history(user_id=user_id, limit=limit)
    return {"count": len(history), "analyses": history}


# -------------------------------------------------
# GET /analyses/{analysis_id}
# -------------------------------------------------

@router.get(
    "/analyses/{analysis_id}",
    summary="Detalle de un análisis específico",
)
async def get_analysis(
    analysis_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: AnalysisService = Depends(get_analysis_service),
):
    """Retorna un análisis por su ID, con URL firmada fresca para el video."""
    analysis = service.get_analysis_detail(analysis_id)

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Análisis no encontrado: {analysis_id}",
        )

    # Seguridad: confirmar que el análisis pertenece al usuario autenticado
    if str(analysis.get("user_id")) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Análisis no encontrado",  # No revelar que existe pero no es tuyo
        )

    return analysis
