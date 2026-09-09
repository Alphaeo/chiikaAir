"""Thin wrapper around MediaPipe's FaceLandmarker (Tasks API), reading
out blendshape scores -- the face equivalent of hand_tracker.py's
HandLandmarker wrapper.

Blendshapes are named, 0..1 scored facial-expression coefficients
(the same ARKit-style set used across the industry -- jawOpen,
mouthSmileLeft, browInnerUp, etc.) that MediaPipe derives from the
468-point face mesh. Reading a named score is far more robust than
computing our own geometry from raw landmarks, the way hand_tracker.py
has to for is_fist().
"""
import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)

MODEL_PATH = "models/face_landmarker.task"


class FaceTracker:
    def __init__(self, min_detection_confidence: float = 0.35):
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_detection_confidence,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        self._timestamp_ms = 0

    def process(self, frame_bgr) -> dict[str, float] | None:
        """Run detection on one BGR frame. Returns {blendshape_name:
        score} for the first detected face, or None if no face is
        found this frame."""
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        self._timestamp_ms += 1
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.face_blendshapes:
            return None
        return {c.category_name: c.score for c in result.face_blendshapes[0]}

    def close(self):
        self._landmarker.close()
