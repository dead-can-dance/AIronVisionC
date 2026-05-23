"""
Analyzer de sentadillas con MediaPipe.

Implementación concreta de BaseExerciseAnalyzer para el ejercicio sentadilla.
Lógica pura de CV: no sabe de DB, ni de MinIO, ni de FastAPI.

Pipeline de video anotado:
1. OpenCV genera un archivo temporal con codec mp4v (rápido)
2. ffmpeg lo reencodea a H.264 (estándar web/mobile)
"""
from __future__ import annotations

import subprocess
import tempfile
from enum import IntEnum
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import (
    PoseLandmarksConnections,
    drawing_styles,
    drawing_utils,
)
from scipy.signal import find_peaks, savgol_filter

from app.modules.cv_feedback.analyzers.base import (
    AnalysisResult,
    BaseExerciseAnalyzer,
)
from app.modules.cv_feedback.schemas import (
    DepthCategory,
    RepDetail,
    SessionSummary,
    VideoMetadata,
)


# =====================================================
# Constantes
# =====================================================

class PoseLandmark(IntEnum):
    """Índices de los 33 landmarks de MediaPipe Pose."""
    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28


# Umbrales biomecánicos para clasificación de profundidad
DEPTH_THRESHOLDS = {
    "atg": 70.0,
    "parallel": 90.0,
    "partial": 120.0,
}

# Parámetros de detección de reps (find_peaks)
REP_DETECTION_PARAMS = {
    "min_angle_threshold": 100.0,
    "min_distance_frames": 30,
    "min_prominence": 20.0,
}

# Parámetros de suavizado Savitzky-Golay
SMOOTHING_WINDOW = 15
SMOOTHING_POLYORDER = 3


# =====================================================
# El analizador
# =====================================================

class SquatAnalyzer(BaseExerciseAnalyzer):
    """Pipeline completo de análisis de sentadilla."""

    @property
    def exercise_type(self) -> str:
        return "squat"

    # -------------------------------------------------
    # Pipeline principal
    # -------------------------------------------------

    def analyze(self, video_path: str | Path) -> AnalysisResult:
        """Ejecuta el pipeline completo sobre un video."""
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video no encontrado: {video_path}")

        metadata = self._inspect_video(video_path)
        df = self._process_video_frames(video_path, metadata)

        if df.empty or not df["pose_detected"].any():
            raise ValueError("No se detectó ninguna pose en el video")

        df_valid = df[df["pose_detected"]].copy().reset_index(drop=True)
        df_valid["knee_angle_smooth"] = savgol_filter(
            df_valid["knee_angle"].values,
            window_length=min(SMOOTHING_WINDOW, len(df_valid) - 1 if len(df_valid) % 2 == 0 else len(df_valid)),
            polyorder=SMOOTHING_POLYORDER,
        )

        reps_data = self._detect_reps(df_valid)
        summary = self._build_summary(df_valid, reps_data)

        return AnalysisResult(
            exercise_type=self.exercise_type,
            video_metadata=metadata,
            summary=summary,
            reps=reps_data,
            full_dataframe=df_valid,
        )

    # -------------------------------------------------
    # Pasos internos del pipeline
    # -------------------------------------------------

    def _inspect_video(self, video_path: Path) -> VideoMetadata:
        """Extrae metadatos del video sin procesar frames."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0.0

            return VideoMetadata(
                filename=video_path.name,
                size_bytes=video_path.stat().st_size,
                duration_sec=round(duration, 2),
                fps=round(fps, 2),
                width=width,
                height=height,
            )
        finally:
            cap.release()

    def _create_detector(self):
        """Crea un PoseLandmarker en modo VIDEO."""
        base_options = mp_python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def _process_video_frames(
        self, video_path: Path, metadata: VideoMetadata
    ) -> pd.DataFrame:
        """Procesa todos los frames con MediaPipe y retorna DataFrame de features."""
        detector = self._create_detector()
        cap = cv2.VideoCapture(str(video_path))

        rows = []
        frame_idx = 0
        try:
            while True:
                ret, frame_bgr = cap.read()
                if not ret:
                    break

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                timestamp_ms = int((frame_idx / metadata.fps) * 1000)
                result = detector.detect_for_video(mp_image, timestamp_ms)

                row: dict = {
                    "frame": frame_idx,
                    "timestamp_sec": frame_idx / metadata.fps,
                    "pose_detected": False,
                }

                if result.pose_landmarks:
                    features = self._extract_frame_features(result.pose_landmarks[0])
                    row["pose_detected"] = True
                    row.update(features)

                rows.append(row)
                frame_idx += 1
        finally:
            cap.release()
            detector.close()

        return pd.DataFrame(rows)

    @staticmethod
    def _calculate_angle_2d(point_a, point_b, point_c) -> float:
        """Ángulo en B formado por A-B-C en grados (0-180)."""
        a = np.array([point_a.x, point_a.y]) if hasattr(point_a, "x") else np.array(point_a)
        b = np.array([point_b.x, point_b.y]) if hasattr(point_b, "x") else np.array(point_b)
        c = np.array([point_c.x, point_c.y]) if hasattr(point_c, "x") else np.array(point_c)

        ba = a - b
        bc = c - b
        mag_ba = np.linalg.norm(ba)
        mag_bc = np.linalg.norm(bc)
        if mag_ba == 0 or mag_bc == 0:
            return 0.0

        cosine = np.clip(np.dot(ba, bc) / (mag_ba * mag_bc), -1.0, 1.0)
        return float(np.degrees(np.arccos(cosine)))

    def _extract_frame_features(self, landmarks) -> dict:
        """Extrae métricas relevantes de un frame con pose detectada."""
        left_vis = np.mean([
            landmarks[PoseLandmark.LEFT_HIP].visibility,
            landmarks[PoseLandmark.LEFT_KNEE].visibility,
            landmarks[PoseLandmark.LEFT_ANKLE].visibility,
        ])
        right_vis = np.mean([
            landmarks[PoseLandmark.RIGHT_HIP].visibility,
            landmarks[PoseLandmark.RIGHT_KNEE].visibility,
            landmarks[PoseLandmark.RIGHT_ANKLE].visibility,
        ])

        if right_vis > left_vis:
            side = "right"
            hip = landmarks[PoseLandmark.RIGHT_HIP]
            knee = landmarks[PoseLandmark.RIGHT_KNEE]
            ankle = landmarks[PoseLandmark.RIGHT_ANKLE]
            shoulder = landmarks[PoseLandmark.RIGHT_SHOULDER]
            side_visibility = right_vis
        else:
            side = "left"
            hip = landmarks[PoseLandmark.LEFT_HIP]
            knee = landmarks[PoseLandmark.LEFT_KNEE]
            ankle = landmarks[PoseLandmark.LEFT_ANKLE]
            shoulder = landmarks[PoseLandmark.LEFT_SHOULDER]
            side_visibility = left_vis

        knee_angle = self._calculate_angle_2d(hip, knee, ankle)

        return {
            "side": side,
            "side_visibility": float(side_visibility),
            "knee_angle": knee_angle,
            "hip_y": hip.y,
            "knee_y": knee.y,
            "shoulder_y": shoulder.y,
            "hip_visibility": float(hip.visibility),
            "knee_visibility": float(knee.visibility),
            "ankle_visibility": float(ankle.visibility),
        }

    def _detect_reps(self, df: pd.DataFrame) -> list[RepDetail]:
        """Detecta repeticiones encontrando mínimos locales en el ángulo de rodilla."""
        inverted = -df["knee_angle_smooth"].values
        peaks_idx, _ = find_peaks(
            inverted,
            height=-REP_DETECTION_PARAMS["min_angle_threshold"],
            distance=REP_DETECTION_PARAMS["min_distance_frames"],
            prominence=REP_DETECTION_PARAMS["min_prominence"],
        )

        reps = []
        for i, idx in enumerate(peaks_idx, start=1):
            row = df.iloc[idx]
            angle = float(row["knee_angle_smooth"])
            reps.append(RepDetail(
                rep_number=i,
                timestamp_sec=round(float(row["timestamp_sec"]), 3),
                min_knee_angle=round(angle, 2),
                depth_category=self._classify_depth(angle),
            ))
        return reps

    @staticmethod
    def _classify_depth(angle: float) -> DepthCategory:
        """Clasifica una rep según su ángulo mínimo."""
        if angle < DEPTH_THRESHOLDS["atg"]:
            return DepthCategory.ATG
        if angle < DEPTH_THRESHOLDS["parallel"]:
            return DepthCategory.PARALLEL
        if angle < DEPTH_THRESHOLDS["partial"]:
            return DepthCategory.PARTIAL
        return DepthCategory.SHALLOW

    def _build_summary(
        self, df: pd.DataFrame, reps: list[RepDetail]
    ) -> SessionSummary:
        """Calcula el resumen estadístico de la sesión."""
        if not reps:
            return SessionSummary(
                total_reps=0,
                duration_sec=0.0,
                min_depth_angle=0.0,
                max_depth_angle=0.0,
                mean_depth_angle=0.0,
                depth_consistency_std=0.0,
                avg_rep_interval_sec=0.0,
                detection_quality=float(df["side_visibility"].mean()),
            )

        rep_angles = [r.min_knee_angle for r in reps]
        rep_times = [r.timestamp_sec for r in reps]
        intervals = np.diff(rep_times) if len(rep_times) > 1 else [0.0]

        return SessionSummary(
            total_reps=len(reps),
            duration_sec=round(rep_times[-1] - rep_times[0], 2) if len(rep_times) > 1 else 0.0,
            min_depth_angle=round(min(rep_angles), 2),
            max_depth_angle=round(max(rep_angles), 2),
            mean_depth_angle=round(float(np.mean(rep_angles)), 2),
            depth_consistency_std=round(float(np.std(rep_angles)), 2),
            avg_rep_interval_sec=round(float(np.mean(intervals)), 2),
            detection_quality=round(float(df["side_visibility"].mean()), 3),
        )

    # -------------------------------------------------
    # Generación de video anotado
    # -------------------------------------------------

    def generate_annotated_video(
        self,
        input_video_path: str | Path,
        output_video_path: str | Path,
        result: AnalysisResult,
    ) -> Path:
        """Genera un video anotado con esqueleto, ángulo y contador de reps.

        Pipeline en dos pasos:
        1. OpenCV genera archivo temporal con codec mp4v
        2. ffmpeg lo reencodea a H.264 (compatible con navegadores y mobile)
        """
        input_path = Path(input_video_path)
        output_path = Path(output_video_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Archivo temporal para la salida intermedia de OpenCV
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            temp_path = Path(tmp.name)

        try:
            self._generate_with_opencv(input_path, temp_path, result)
            self._reencode_to_h264(temp_path, output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

        return output_path

    def _generate_with_opencv(
        self,
        input_path: Path,
        output_path: Path,
        result: AnalysisResult,
    ) -> None:
        """Genera el video anotado usando OpenCV. Salida intermedia con codec mp4v."""
        detector = self._create_detector()
        cap = cv2.VideoCapture(str(input_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        if not writer.isOpened():
            cap.release()
            detector.close()
            raise RuntimeError(f"No se pudo abrir el writer para {output_path}")

        df = result.full_dataframe
        reps_total = len(result.reps)
        rep_timestamps = [r.timestamp_sec for r in result.reps]

        try:
            frame_idx = 0
            while True:
                ret, frame_bgr = cap.read()
                if not ret:
                    break

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                timestamp_ms = int((frame_idx / fps) * 1000)
                detection = detector.detect_for_video(mp_image, timestamp_ms)

                current_time = frame_idx / fps
                reps_completed = sum(1 for t in rep_timestamps if t < current_time)
                current_rep = min(reps_completed + 1, reps_total) if reps_total > 0 else 0

                frame_data = self._get_frame_data(df, frame_idx)

                annotated = self._annotate_frame(
                    frame_bgr,
                    detection,
                    frame_data,
                    current_rep,
                    reps_completed,
                    reps_total,
                    width,
                    height,
                )
                writer.write(annotated)
                frame_idx += 1
        finally:
            cap.release()
            writer.release()
            detector.close()

    @staticmethod
    def _reencode_to_h264(input_path: Path, output_path: Path) -> None:
        """Reencodea un video a H.264 usando ffmpeg para compatibilidad universal.

        Args:
            input_path: Video temporal generado por OpenCV (codec mp4v).
            output_path: Destino final con codec H.264.
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg falló al reencodear:\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )

    @staticmethod
    def _get_frame_data(df: pd.DataFrame, frame_idx: int) -> dict:
        """Obtiene los datos calculados de un frame específico del DataFrame."""
        match = df[df["frame"] == frame_idx]
        if match.empty:
            return {"pose_detected": False}
        row = match.iloc[0]
        return {
            "pose_detected": True,
            "knee_angle_smooth": float(row["knee_angle_smooth"]),
        }

    @staticmethod
    def _annotate_frame(
        frame_bgr: np.ndarray,
        detection_result,
        frame_data: dict,
        current_rep: int,
        reps_completed: int,
        reps_total: int,
        width: int,
        height: int,
    ) -> np.ndarray:
        """Dibuja esqueleto, contador de reps y ángulo sobre un frame."""
        annotated = frame_bgr.copy()

        # 1. Esqueleto
        if detection_result and detection_result.pose_landmarks:
            connection_style = drawing_utils.DrawingSpec(
                color=(0, 255, 100),
                thickness=3,
            )
            for pose_landmarks in detection_result.pose_landmarks:
                drawing_utils.draw_landmarks(
                    image=annotated,
                    landmark_list=pose_landmarks,
                    connections=PoseLandmarksConnections.POSE_LANDMARKS,
                    landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
                    connection_drawing_spec=connection_style,
                )

        # 2. Panel superior semi-transparente
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (width, 180), (0, 0, 0), -1)
        annotated = cv2.addWeighted(overlay, 0.55, annotated, 0.45, 0)

        # 3. Contador de reps (izquierda)
        rep_text = f"REP {current_rep}/{reps_total}"
        cv2.putText(annotated, rep_text, (40, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 5)
        cv2.putText(annotated, rep_text, (40, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 255, 200), 3)

        completed_text = f"Completadas: {reps_completed}"
        cv2.putText(annotated, completed_text, (40, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)

        # 4. Ángulo (derecha)
        if frame_data.get("pose_detected"):
            angle = frame_data["knee_angle_smooth"]
            if angle < 70:
                angle_color = (0, 255, 100)
                depth_label = "ATG"
            elif angle < 90:
                angle_color = (0, 220, 255)
                depth_label = "PARALELO"
            elif angle < 120:
                angle_color = (0, 165, 255)
                depth_label = "PARCIAL"
            else:
                angle_color = (200, 200, 200)
                depth_label = "DE PIE"

            angle_text = f"{angle:.0f}"
            cv2.putText(annotated, angle_text, (width - 280, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 255), 7)
            cv2.putText(annotated, angle_text, (width - 280, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 3.0, angle_color, 4)
            cv2.putText(annotated, "deg", (width - 130, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            cv2.putText(annotated, depth_label, (width - 280, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, angle_color, 2)

        # 5. Watermark
        cv2.putText(annotated, "AIronVision", (width - 320, height - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 200), 2)

        return annotated
