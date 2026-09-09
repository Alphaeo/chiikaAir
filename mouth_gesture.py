"""Shared mouth-gesture helpers, used by both mouth_launcher.py (the
standalone demo) and screenshot_gallery.py (the main app).
"""
import subprocess

import win32api
import win32con

MOUTH_O_ROUNDNESS_THRESHOLD = 0.45
MOUTH_O_JAW_THRESHOLD = 0.15
MOUTH_O_HOLD_SECONDS = 0.4


def mouth_roundness(blendshapes: dict[str, float] | None) -> float:
    """How "O"-shaped the mouth currently is. Combines the two closest
    ARKit-style blendshapes to a rounded-open mouth -- mouthFunnel
    (lips pushed into a funnel/circle, like "ooh") and mouthPucker
    (lips pressed and pushed forward) -- since which one scores higher
    for a given person's "O" varies."""
    if not blendshapes:
        return 0.0
    return max(blendshapes.get("mouthFunnel", 0.0), blendshapes.get("mouthPucker", 0.0))


def is_mouth_o(blendshapes: dict[str, float] | None) -> bool:
    """True only when the mouth is both rounded (funnel/pucker) AND the
    jaw is open. Roundness alone fired on a resting/talking face too
    often -- requiring the jaw to actually be open is what separates a
    deliberate "O" from ordinary lip movement."""
    if not blendshapes:
        return False
    roundness = mouth_roundness(blendshapes)
    jaw_open = blendshapes.get("jawOpen", 0.0)
    return roundness > MOUTH_O_ROUNDNESS_THRESHOLD and jaw_open > MOUTH_O_JAW_THRESHOLD


def is_process_running(image_name: str) -> bool:
    """Checks via `tasklist` (stdlib subprocess only, no extra
    dependency like psutil) whether a process with this exact image
    name (e.g. "EXCEL.EXE") is currently running. Only call this right
    when a gesture actually fires, not every frame -- spawning
    `tasklist` takes real time, unlike a landmark/blendshape check."""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return image_name.lower() in result.stdout.lower()


def open_task_view() -> None:
    """Simulates the Win+Tab shortcut via synthetic key events."""
    win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_TAB, 0, 0, 0)
    win32api.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
