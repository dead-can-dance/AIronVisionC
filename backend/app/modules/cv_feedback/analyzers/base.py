"""
Clase base abstracta para analyzers de ejercicios.

Cualquier ejercicio futuro (peso muerto, press de banca, dominadas, etc.)
debe heredar de esta clase y implementar sus métodos abstractos.

Esto garantiza una API uniforme: el orquestador no necesita saber
qué ejercicio está analizando — todos se comportan igual hacia afuera.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from app.modules.cv_feedback.schemas import (
    RepDetail,
    SessionSummary,
    VideoMetadata,
)


@dataclass
class AnalysisResult:
    """Resultado estandarizado de cualquier análisis de ejercicio."""
    exercise_type: str
    video_metadata: VideoMetadata
    summary: SessionSummary
    reps: list[RepDetail]
    full_dataframe: pd.DataFrame
    annotated_video_path: Optional[Path] = None


class BaseExerciseAnalyzer(ABC):
    """
    Contrato que cualquier analyzer de ejercicio debe cumplir.

    Métodos abstractos (cada ejercicio los implementa):
    - exercise_type: identificador del ejercicio (ej. "squat", "deadlift")
    - analyze: pipeline completo de análisis
    - generate_annotated_video: genera video con overlay
    """

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Modelo MediaPipe no encontrado: {self.model_path}"
            )

    @property
    @abstractmethod
    def exercise_type(self) -> str:
        """Identificador único del ejercicio (ej. 'squat')."""
        ...

    @abstractmethod
    def analyze(self, video_path: str | Path) -> AnalysisResult:
        """Ejecuta el pipeline de análisis sobre un video."""
        ...

    @abstractmethod
    def generate_annotated_video(
        self,
        input_video_path: str | Path,
        output_video_path: str | Path,
        result: AnalysisResult,
    ) -> Path:
        """Genera un video anotado con los overlays del ejercicio."""
        ...
