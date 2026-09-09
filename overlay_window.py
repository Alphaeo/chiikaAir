"""Turns a plain OpenCV window into a small borderless, always-on-top
panel that can be pinned to a screen corner or blown up to fullscreen
(Windows only, via pywin32).

OpenCV's own window API (highgui) has no concept of "borderless",
"always on top" or "resize to an arbitrary rect" -- but the window it
creates is a real Win32 window under the hood, so we grab its handle
by title and restyle/reposition it directly.
"""
import win32api
import win32con
import win32gui


def find_hwnd(window_title: str):
    return win32gui.FindWindow(None, window_title) or None


def strip_chrome(hwnd) -> None:
    """Remove the title bar and resize border, once, for good."""
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~win32con.WS_CAPTION
    style &= ~win32con.WS_THICKFRAME
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)


def move_resize(hwnd, x: int, y: int, width: int, height: int) -> None:
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, x, y, width, height,
        win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
    )


def screen_size() -> tuple[int, int]:
    return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def corner_position(width: int, height: int, corner: str = "bottom-right",
                     margin: int = 20) -> tuple[int, int]:
    screen_w, screen_h = screen_size()
    v, h = corner.split("-")
    x = margin if h == "left" else screen_w - width - margin
    y = margin if v == "top" else screen_h - height - margin
    return x, y


def pin_to_corner(window_title: str, width: int, height: int,
                   corner: str = "bottom-right", margin: int = 20):
    """Find the window, strip its chrome and pin it to a screen corner.

    Must be called AFTER at least one cv2.imshow() + cv2.waitKey() for
    the window, so Windows has actually mapped it. Returns the window
    handle on success, or None if the window isn't ready yet -- callers
    should keep retrying on the next frame until this returns a handle.
    """
    hwnd = find_hwnd(window_title)
    if not hwnd:
        return None
    strip_chrome(hwnd)
    x, y = corner_position(width, height, corner, margin)
    move_resize(hwnd, x, y, width, height)
    return hwnd
