# MediaPipe Models

Esta carpeta contiene los modelos de pose estimation de MediaPipe.

**Los archivos `.task` NO están en git** (pesan ~30 MB cada uno).
Para obtener los modelos necesarios:

```bash
# Modelo principal (usado por SquatAnalyzer)
wget -O pose_landmarker_heavy.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task
```

## Variantes disponibles

| Modelo | Tamaño | Precisión | Velocidad | Uso |
|---|---|---|---|---|
| `pose_landmarker_lite` | 5 MB | Buena | Rápido | Mobile, tiempo real |
| `pose_landmarker_full` | 9 MB | Mejor | Medio | Balance |
| `pose_landmarker_heavy` | 30 MB | Mejor | Lento | Backend, análisis preciso |

Actualmente usamos **heavy** para máxima precisión en análisis batch.
