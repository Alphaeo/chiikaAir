"""Fine wrapper around MediaPipe's HandLandmarker (Tasks API).

Feeds webcam frames in and returns hand landmarks in pixel coordinates,
so the demo scripts don't have to deal with MediaPipe's API directly.
"""
import math
from dataclasses import dataclass

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)

MODEL_PATH = "models/hand_landmarker.task"

# Landmark indices we care about (see MediaPipe's 21-point hand model).
WRIST = 0
THUMB_TIP = 4
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_PIP = 18
PINKY_TIP = 20

# (fingertip, lower-knuckle) pairs used by Hand.is_fist() -- thumb excluded,
# its curl geometry is different enough to need its own heuristic.
_CURL_PAIRS = [
    (INDEX_TIP, INDEX_PIP),
    (MIDDLE_TIP, MIDDLE_PIP),
    (RING_TIP, RING_PIP),
    (PINKY_TIP, PINKY_PIP),
]


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Hand:
    landmarks: list  # list of (x, y) pixel coordinates, 21 points
    handedness: str  # "Left" or "Right"

    def point(self, index: int) -> tuple[int, int]:
        return self.landmarks[index]

    def is_fist(self, min_curled: int = 4) -> bool:
        """True when at least `min_curled` of the 4 fingers (thumb
        excluded) are curled toward the palm.

        A finger counts as curled when its tip sits closer to the
        wrist than its own lower knuckle (PIP) does -- true regardless
        of how the hand is rotated in frame, unlike comparing raw
        pixel heights. Requiring all 4 (not just 3) matters: a plain
        pointing pose (index out, other three curled) already curls 3
        of 4 and would otherwise be read as a fist.
        """
        wrist = self.point(WRIST)
        curled = sum(
            1
            for tip_idx, pip_idx in _CURL_PAIRS
            if _distance(self.point(tip_idx), wrist) < _distance(self.point(pip_idx), wrist)
        )
        return curled >= min_curled


class HandTracker:
    def __init__(self, num_hands: int = 2, min_detection_confidence: float = 0.6):
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_detection_confidence,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        self._timestamp_ms = 0

    def process(self, frame_bgr) -> list[Hand]:
        """Run detection on one BGR frame, return the hands found."""
        height, width = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        self._timestamp_ms += 1
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        hands = []
        for hand_landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            pixel_points = [
                (int(lm.x * width), int(lm.y * height)) for lm in hand_landmarks
            ]
            hands.append(Hand(landmarks=pixel_points, handedness=handedness[0].category_name))
        return hands

    def close(self):
        self._landmarker.close()
