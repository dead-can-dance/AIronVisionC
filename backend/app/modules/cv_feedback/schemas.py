"""
Schemas Pydantic para el módulo cv_feedback.
Definen la forma de los datos en requests y responses.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# Enums
# =====================================================

class DepthCategory(str, Enum):
    """Clasificación de profundidad de una sentadilla."""
    ATG = "atg"            # < 70°, "ass to grass", profundidad máxima
    PARALLEL = "parallel"  # 70°-90°, paralelo de competencia
    PARTIAL = "partial"    # 90°-120°, sentadilla parcial
    SHALLOW = "shallow"    # > 120°, profundidad insuficiente


class AnalysisStatus(str, Enum):
    """Estado del procesamiento de un análisis."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =====================================================
# Schemas internos del análisis
# =====================================================

class RepDetail(BaseModel):
    """Detalle de una repetición individual."""
    rep_number: int = Field(..., description="Número de la rep dentro de la serie")
    timestamp_sec: float = Field(..., description="Segundo del video donde está el valle")
    min_knee_angle: float = Field(..., description="Ángulo de rodilla más cerrado alcanzado")
    depth_category: DepthCategory


class VideoMetadata(BaseModel):
    """Metadatos del video procesado."""
    filename: str
    size_bytes: int
    duration_sec: float
    fps: float
    width: int
    height: int


class SessionSummary(BaseModel):
    """Resumen estadístico de una sesión completa."""
    total_reps: int
    duration_sec: float = Field(..., description="Tiempo entre primera y última rep")
    min_depth_angle: float = Field(..., description="Rep más profunda (ángulo más bajo)")
    max_depth_angle: float = Field(..., description="Rep menos profunda (ángulo más alto)")
    mean_depth_angle: float
    depth_consistency_std: float = Field(..., description="Desviación estándar de profundidad entre reps")
    avg_rep_interval_sec: float
    detection_quality: float = Field(..., description="Visibility promedio (0-1)")


# =====================================================
# Response del endpoint principal
# =====================================================

class SquatAnalysisResponse(BaseModel):
    """Response completo del endpoint analyze-squat."""
    analysis_id: UUID
    status: AnalysisStatus
    video_metadata: VideoMetadata
    summary: SessionSummary
    reps: list[RepDetail]
    annotated_video_url: Optional[str] = Field(
        None,
        description="URL firmada (temporal) para descargar el video anotado"
    )
    processed_at: datetime
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "video_metadata": {
                    "filename": "Sentadilla_Test.mp4",
                    "size_bytes": 50000000,
                    "duration_sec": 23.7,
                    "fps": 30.0,
                    "width": 1080,
                    "height": 1920,
                },
                "summary": {
                    "total_reps": 7,
                    "duration_sec": 19.2,
                    "min_depth_angle": 55.1,
                    "max_depth_angle": 59.2,
                    "mean_depth_angle": 56.8,
                    "depth_consistency_std": 1.6,
                    "avg_rep_interval_sec": 3.2,
                    "detection_quality": 0.96,
                },
                "reps": [
                    {
                        "rep_number": 1,
                        "timestamp_sec": 3.20,
                        "min_knee_angle": 59.2,
                        "depth_category": "atg",
                    }
                ],
                "annotated_video_url": "http://86.38.217.248:9000/aironvision-videos/...",
                "processed_at": "2026-05-02T20:00:00Z",
            }
        }
    }


# =====================================================
# Errores
# =====================================================

class AnalysisError(BaseModel):
    """Response cuando algo falla."""
    error_code: str
    message: str
    detail: Optional[str] = None
