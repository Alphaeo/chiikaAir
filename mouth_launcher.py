"""Mouth-gesture app launcher: shape your mouth into an "O" to open
Excel; make the same "O" again once Excel is open to bring up Windows'
Task View (Win+Tab) instead of opening a second Excel window.

Uses MediaPipe's FaceLandmarker with blendshapes -- the face equivalent
of hand_tracker.py's HandLandmarker. The "O" shape is read off the
`mouthFunnel` blendshape (lips rounded and parted, the exact shape of
pronouncing "oh") the same way is_fist() reads finger-curl geometry:
a threshold, held briefly via HoldTimer, re-armed once the mouth
relaxes.

This is a small standalone test of face-blendshape gestures, kept
separate from screenshot_gallery.py -- merge later if it proves out.

Known simplification: Excel's "open" state is tracked with a plain
flag, not by checking whether the process is still running -- closing
Excel by hand won't be noticed, and the next "O" will trigger Task
View instead of relaunching it.

Controls:
  q   quit
"""
import ctypes
import os

import cv2
import win32api
import win32con

from face_tracker import FaceTracker
from hold_timer import HoldTimer
from overlay_window import pin_to_corner

ctypes.windll.user32.SetProcessDPIAware()

WINDOW_TITLE = "Mouth Launcher"
WINDOW_W, WINDOW_H = 360, 280

MOUTH_O_THRESHOLD = 0.5
MOUTH_O_HOLD_SECONDS = 0.4


def open_task_view() -> None:
    """Simulates the Win+Tab shortcut via synthetic key events."""
    win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_TAB, 0, 0, 0)
    win32api.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    tracker = FaceTracker()

    mouth_timer = HoldTimer()
    mouth_armed = True
    excel_launched = False
    hwnd = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            frame = cv2.resize(frame, (WINDOW_W, WINDOW_H))

            blendshapes = tracker.process(frame)
            funnel = blendshapes.get("mouthFunnel", 0.0) if blendshapes else 0.0
            is_o = funnel > MOUTH_O_THRESHOLD

            held = mouth_timer.update(is_o)
            if not is_o:
                mouth_armed = True
            if mouth_armed and held >= MOUTH_O_HOLD_SECONDS:
                if not excel_launched:
                    os.startfile("excel")
                    excel_launched = True
                else:
                    open_task_view()
                mouth_armed = False

            status = ("Excel ouvert -- 'O' suivant = Vue des taches"
                      if excel_launched else "Faites un 'O' pour ouvrir Excel")
            cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
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
