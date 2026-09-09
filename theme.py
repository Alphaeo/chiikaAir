"""Shared visual language for the app: one color palette and a couple
of drawing helpers, instead of ad-hoc BGR tuples scattered across
every file. Colors are OpenCV's native BGR order.
"""
import cv2

# Base palette -- a dark, low-saturation panel with a single bright
# accent, instead of the primary-color rectangles/circles OpenCV demos
# usually default to.
BG_PANEL = (38, 32, 28)          # near-black warm slate, for glass panels
BORDER = (90, 84, 78)            # neutral, unselected element border
TEXT_PRIMARY = (235, 232, 228)   # soft off-white, not pure white
TEXT_MUTED = (150, 145, 140)

ACCENT = (232, 193, 71)          # cyan-teal accent (selection, active state)
ACCENT_SOFT = (150, 120, 40)     # dimmer accent, for progress-bar tracks
SUCCESS = (110, 200, 90)         # confirmations (run, capture progress)
DANGER = (70, 70, 225)           # delete / destructive state
LINK = (215, 205, 195)           # link lines between blocks

# A small rotating palette for freshly created blocks (BGR).
BLOCK_PALETTE = [
    (68, 121, 214),   # warm orange
    (100, 181, 129),  # sage green
    (200, 158, 84),   # steel teal
    (196, 120, 176),  # dusty purple
    (94, 197, 214),   # amber
    (99, 99, 209),    # muted red
]

CODE_BG = (26, 24, 22)  # near-black, slightly warm


def draw_rounded_rect(img, top_left, bottom_right, radius, color, thickness=-1):
    x1, y1 = top_left
    x2, y2 = bottom_right
    radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if thickness < 0:
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1, cv2.LINE_AA)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1, cv2.LINE_AA)
        for cx, cy in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius),
                       (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
            cv2.circle(img, (cx, cy), radius, color, -1, cv2.LINE_AA)
    else:
        cv2.line(img, (x1 + radius, y1), (x2 - radius, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + radius, y2), (x2 - radius, y2), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + radius), (x1, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + radius), (x2, y2 - radius), color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def draw_glass_panel(img, top_left, bottom_right, radius=10, color=BG_PANEL, opacity=0.55):
    """A translucent rounded panel blended into `img` -- the "frosted
    glass" backing modern overlay UIs put behind buttons/readouts
    instead of drawing them straight onto the live video."""
    x1, y1 = top_left
    x2, y2 = bottom_right
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, img.shape[1]), min(y2, img.shape[0])
    if x2 <= x1 or y2 <= y1:
        return
    overlay = img.copy()
    draw_rounded_rect(overlay, (x1, y1), (x2, y2), radius, color, -1)
    cv2.addWeighted(overlay, opacity, img, 1 - opacity, 0, dst=img)


def put_text(img, text, org, scale=0.5, color=TEXT_PRIMARY, thickness=1):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
