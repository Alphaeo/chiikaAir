"""Mouth-gesture app launcher: shape your mouth into an "O" to open
Excel; make the same "O" again to bring up Windows' Task View
(Win+Tab) if Excel is already running, or relaunch it if you closed it
manually -- checked live via `tasklist`, not a stale internal flag.

Uses MediaPipe's FaceLandmarker with blendshapes -- the face equivalent
of hand_tracker.py's HandLandmarker. The "O" shape requires both a
rounded mouth (mouthFunnel/mouthPucker) AND an open jaw (jawOpen) --
roundness alone fired too easily on an ordinary resting/talking face.
See mouth_gesture.py for the exact thresholds.

This is a standalone test of face-blendshape gestures. The same
mouth_gesture.py helpers are also wired into screenshot_gallery.py's
main app -- this script exists to try the gesture in isolation, with a
live diagnostic readout, without the rest of the app's UI in the way.

Controls:
  q   quit
"""
import ctypes
import os

import cv2

from face_tracker import FaceTracker
from hold_timer import HoldTimer
from mouth_gesture import (
    MOUTH_O_HOLD_SECONDS,
    MOUTH_O_JAW_THRESHOLD,
    MOUTH_O_ROUNDNESS_THRESHOLD,
    is_mouth_o,
    is_process_running,
    mouth_roundness,
    open_task_view,
)
from overlay_window import pin_to_corner

ctypes.windll.user32.SetProcessDPIAware()

WINDOW_TITLE = "Mouth Launcher"
WINDOW_W, WINDOW_H = 360, 280

EXCEL_IMAGE_NAME = "EXCEL.EXE"


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    tracker = FaceTracker()

    mouth_timer = HoldTimer()
    mouth_armed = True
    hwnd = None

    try:
        while True:
            ok, raw_frame = cap.read()
            if not ok:
                break
            raw_frame = cv2.flip(raw_frame, 1)

            # Track at native webcam resolution for accuracy -- MediaPipe's
            # face detector is noticeably less reliable on a pre-shrunk
            # 360x280 image, only resize for display below.
            blendshapes = tracker.process(raw_frame)
            frame = cv2.resize(raw_frame, (WINDOW_W, WINDOW_H))

            face_found = blendshapes is not None
            is_o = is_mouth_o(blendshapes)

            held = mouth_timer.update(is_o)
            if not is_o:
                mouth_armed = True
            if mouth_armed and held >= MOUTH_O_HOLD_SECONDS:
                if is_process_running(EXCEL_IMAGE_NAME):
                    open_task_view()
                else:
                    os.startfile("excel")
                mouth_armed = False

            cv2.putText(frame, "'O' : ouvre Excel, ou Vue des taches s'il tourne deja",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            # Live diagnostic readout -- lets you see whether a face is even
            # being found and what score your "O" actually reaches, instead
            # of guessing why nothing triggers.
            face_status = f"visage: {'detecte' if face_found else 'NON DETECTE'}"
            cv2.putText(frame, face_status, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0) if face_found else (0, 0, 255), 1)
            roundness = mouth_roundness(blendshapes)
            jaw_open = blendshapes.get("jawOpen", 0.0) if blendshapes else 0.0
            cv2.putText(frame, f"rondeur {roundness:.2f} (seuil {MOUTH_O_ROUNDNESS_THRESHOLD})"
                                f"  jaw {jaw_open:.2f} (seuil {MOUTH_O_JAW_THRESHOLD})",
                        (10, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)

            pct = 1.0 if not mouth_armed else min(held / MOUTH_O_HOLD_SECONDS, 1.0)
            bar_color = (0, 255, 0) if is_o else (100, 100, 100)
            cv2.rectangle(frame, (10, WINDOW_H - 20), (10 + int(100 * pct), WINDOW_H - 12), bar_color, -1)

            cv2.imshow(WINDOW_TITLE, frame)
            if hwnd is None:
                hwnd = pin_to_corner(WINDOW_TITLE, WINDOW_W, WINDOW_H, corner="bottom-left")

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
