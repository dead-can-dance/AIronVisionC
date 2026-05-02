# Notas de validación de Computer Vision — abr 2026

## Validado ✅

- **MediaPipe Pose Heavy** detecta sentadillas con visibility >0.95 en video casero (1080x1920, 30fps)
- **Procesamiento real-time-ish:** 23.5 fps en CPU (sin GPU), video 23s procesado en 30s
- **Detección de reps automática** funciona perfectamente con `scipy.signal.find_peaks` sobre la curva suavizada de ángulo de rodilla
- **Auto-selección de lado** (izquierdo vs derecho según visibility) funciona estable
- **Robusto a fondo con ruido visual** (cocina con muebles, electrodomésticos, etc.)
- **Suavizado Savitzky-Golay** con window=15, polyorder=3 elimina ruido sin distorsionar picos

## Métricas extraíbles por rep
- Ángulo mínimo de rodilla (profundidad)
- Tiempo de rep
- Cadencia entre reps
- Tendencia de profundidad (detecta fatiga)
- Inclinación de torso (en `torso_angle`, aún no analizado)

## Pendiente / por validar
- Detección de errores técnicos (valgo de rodilla, espalda redondeada)
- Comportamiento con múltiples personas en frame
- Comportamiento con video horizontal (vs vertical actual)
- Comportamiento con iluminación pobre
- Performance en celular (móvil) vs desktop
- Otros ejercicios (peso muerto, press de banca)

## Decisiones técnicas tomadas
- **Modelo:** `pose_landmarker_heavy.task` (max precisión, no real-time en móvil)
- **Procesamiento 2D:** sentadilla en plano sagital, z se ignora
- **Umbral visibility:** 0.5 mínimo para confiar en un landmark
- **Convención:** invertir eje Y en gráficas de ángulo de rodilla para legibilidad
