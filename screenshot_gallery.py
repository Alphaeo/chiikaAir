"""Floating webcam PiP pinned to a screen corner, with a gesture-driven
screenshot gallery and draggable, linkable text/code blocks.

Screenshots:
  - Make a fist and hold it ~0.4s -> captures a screenshot of your
    screen, added as a thumbnail to the gallery (top-right, newest on
    top, max 4 -- the oldest is dropped to make room). Open your hand
    fully before you can capture again.
  - Point at (hover over) a thumbnail with your index finger -> it
    becomes the selected photo, shown enlarged over the webcam feed.

Blocks:
  - Hover the "+" button (top-left) to create a text block, or the
    "<>" button just below it for a code block (dark gray/black) --
    max 4 blocks total. Pinch on a block to drag it; drag it onto the
    trash button (bottom-right) and hold briefly to delete it.
  - Point at a block to select it.
  - Draw a circle in the air with your index finger while it's over a
    block (the block's border turns magenta while a link is pending),
    then point at a second block -> links the two. Linked blocks are
    always shown connected by an arrow in the corner view. While a
    linked block is zoomed (see below), the same arrow appears on its
    right edge -- hover it to jump straight to the linked block (and
    so on, if that one is linked too).

Either kind (selected photo or selected block):
  - Spread your thumb and index apart -> it takes over the whole
    screen. Pinch them back together -> shrinks back to the corner.
  - A zoomed text or code block accepts typed text directly
    (backspace/enter work; Escape or a pinch returns to the corner).
    On a code block, make a fist and hold it ~0.4s to run the code
    (via Python's exec -- no sandboxing, it's your own code on your
    own machine); the output is shown below it.

Controls:
  q   quit (disabled while typing into a block -- pinch/Escape out first)
  c   clear the gallery and all blocks
"""
import ctypes
import time
from collections import deque

import cv2
import mss
import numpy as np

from blocks import BUTTON_TEXT_RECT, BUTTON_CODE_RECT, BlockManager
from circle_gesture import CircleDetector
from code_runner import run_code
from hand_tracker import HandTracker, THUMB_TIP, INDEX_TIP
from hold_timer import HoldTimer
from overlay_window import pin_to_corner, move_resize, corner_position, screen_size

# Windows scales screenshots to match display scaling (125%, 150%...)
# unless the process declares itself DPI-aware -- without this call
# mss captures come out blurry/mis-sized on HiDPI screens.
ctypes.windll.user32.SetProcessDPIAware()

WINDOW_TITLE = "Webcam Overlay"
CORNER_W, CORNER_H = 420, 320

THUMB_W, THUMB_H = 96, 64
THUMB_MARGIN = 8
MAX_THUMBNAILS = 4

FIST_HOLD_SECONDS = 0.4
HOVER_HOLD_SECONDS = 0.15
SPREAD_HOLD_SECONDS = 0.3
PINCH_HOLD_SECONDS = 0.3
SPREAD_THRESHOLD_PX = 150
PINCH_THRESHOLD_PX = 40
LINK_TIMEOUT_SECONDS = 5.0

STATE_CORNER = "corner"
STATE_FULLSCREEN = "fullscreen"


def _distance(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def grab_screenshot(sct, monitor) -> np.ndarray:
    shot = sct.grab(monitor)
    return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)


def thumbnail_rects(count: int, window_w: int) -> list[tuple[int, int, int, int]]:
    """Top-right stack of thumbnail rectangles, newest first."""
    rects = []
    for i in range(count):
        x1 = window_w - THUMB_MARGIN - THUMB_W
        y1 = THUMB_MARGIN + i * (THUMB_H + THUMB_MARGIN)
        rects.append((x1, y1, x1 + THUMB_W, y1 + THUMB_H))
    return rects


def point_in_rect(point, rect) -> bool:
    x, y = point
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


# Trims this fraction off each edge of the webcam frame before mapping it to
# the full screen in block-fullscreen mode. Without it, a target near the
# screen edge (like the link arrow) maps back to a spot right at the physical
# edge of the camera's view -- where the hand is half out of frame and
# tracking is least reliable, making it effectively unreachable.
FULLSCREEN_HAND_MARGIN = 0.15


def map_to_screen(x, y, native_w, native_h, screen_w, screen_h, margin=FULLSCREEN_HAND_MARGIN):
    inner_w = native_w * (1 - 2 * margin)
    inner_h = native_h * (1 - 2 * margin)
    x_adj = min(max(x - native_w * margin, 0), inner_w)
    y_adj = min(max(y - native_h * margin, 0), inner_h)
    return int(x_adj / inner_w * screen_w), int(y_adj / inner_h * screen_h)


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)

    tracker = HandTracker(num_hands=1)
    sct = mss.MSS()
    monitor = sct.monitors[1]

    gallery = deque(maxlen=MAX_THUMBNAILS)  # newest-first: {"full", "thumb"}
    selected_index = None
    block_manager = BlockManager(CORNER_W, CORNER_H)
    selected_block_id = None
    linking_from = None
    linking_from_time = 0.0
    circle_detector = CircleDetector()

    fist_timer = HoldTimer()
    fist_armed = True
    hover_timer = HoldTimer()
    hover_candidate = None
    text_button_timer = HoldTimer()
    text_button_armed = True
    code_button_timer = HoldTimer()
    code_button_armed = True
    block_hover_timer = HoldTimer()
    block_hover_candidate = None
    spread_timer = HoldTimer()
    pinch_timer = HoldTimer()
    arrow_hover_timer = HoldTimer()
    run_timer = HoldTimer()
    run_armed = True
    smoothed_index_pt = None  # light EMA smoothing for the fullscreen cursor

    state = STATE_CORNER
    fullscreen_kind = None  # "photo" or "block"
    fullscreen_block_id = None
    hwnd = None

    def enter_fullscreen(kind, block_id=None):
        nonlocal state, fullscreen_kind, fullscreen_block_id, pinch_timer, arrow_hover_timer, run_timer, run_armed, smoothed_index_pt
        state = STATE_FULLSCREEN
        fullscreen_kind = kind
        fullscreen_block_id = block_id
        pinch_timer = HoldTimer()
        arrow_hover_timer = HoldTimer()
        run_timer = HoldTimer()
        run_armed = True
        smoothed_index_pt = None
        sw, sh = screen_size()
        move_resize(hwnd, 0, 0, sw, sh)

    def return_to_corner():
        nonlocal state, selected_index, selected_block_id, spread_timer
        state = STATE_CORNER
        selected_index = None
        selected_block_id = None
        spread_timer = HoldTimer()
        x, y = corner_position(CORNER_W, CORNER_H, corner="bottom-right")
        move_resize(hwnd, x, y, CORNER_W, CORNER_H)

    try:
        while True:
            ok, raw_frame = cap.read()
            if not ok:
                break
            raw_frame = cv2.flip(raw_frame, 1)
            native_h, native_w = raw_frame.shape[:2]

            hands = tracker.process(raw_frame)
            hand = hands[0] if hands else None

            pinch_dist = None
            if hand is not None:
                pinch_dist = _distance(hand.point(THUMB_TIP), hand.point(INDEX_TIP))

            typing_mode = state == STATE_FULLSCREEN and fullscreen_kind == "block"

            if state == STATE_CORNER:
                # --- capture gesture: closed fist, held, re-armed on open hand ---
                is_fist = hand is not None and hand.is_fist()
                fist_held = fist_timer.update(is_fist)
                if not is_fist:
                    fist_armed = True
                if fist_armed and fist_held >= FIST_HOLD_SECONDS:
                    shot = grab_screenshot(sct, monitor)
                    thumb = cv2.resize(shot, (THUMB_W, THUMB_H))
                    gallery.appendleft({"full": shot, "thumb": thumb})
                    fist_armed = False

                if selected_index is not None and selected_index >= len(gallery):
                    selected_index = None  # gallery shrank/cleared under us

                frame = cv2.resize(raw_frame, (CORNER_W, CORNER_H))
                scale_x, scale_y = CORNER_W / native_w, CORNER_H / native_h

                # --- scaled fingertip positions, shared by everything below ---
                index_pt = thumb_pt = pinch_point = None
                is_pinching = False
                if hand is not None:
                    ix, iy = hand.point(INDEX_TIP)
                    index_pt = (int(ix * scale_x), int(iy * scale_y))
                    tx, ty = hand.point(THUMB_TIP)
                    thumb_pt = (int(tx * scale_x), int(ty * scale_y))
                    pinch_point = ((index_pt[0] + thumb_pt[0]) // 2, (index_pt[1] + thumb_pt[1]) // 2)
                    is_pinching = pinch_dist is not None and pinch_dist < PINCH_THRESHOLD_PX

                # --- hover gesture: index fingertip over a thumbnail selects it ---
                rects = thumbnail_rects(len(gallery), CORNER_W)
                hovered_now = None
                if index_pt is not None:
                    for i, rect in enumerate(rects):
                        if point_in_rect(index_pt, rect):
                            hovered_now = i
                            break

                if hovered_now != hover_candidate:
                    hover_candidate = hovered_now
                    hover_timer = HoldTimer()
                if hovered_now is not None and hover_timer.update(True) >= HOVER_HOLD_SECONDS:
                    selected_index = hovered_now
                    selected_block_id = None

                for i, (item, rect) in enumerate(zip(gallery, rects)):
                    x1, y1, x2, y2 = rect
                    frame[y1:y2, x1:x2] = item["thumb"]
                    color = (0, 255, 255) if i == selected_index else (255, 255, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # --- "+"/"<>" buttons: hover to create a block, must leave before another fires ---
                hovering_text_button = index_pt is not None and point_in_rect(index_pt, BUTTON_TEXT_RECT)
                text_button_held = text_button_timer.update(hovering_text_button)
                if not hovering_text_button:
                    text_button_armed = True
                if text_button_armed and text_button_held >= HOVER_HOLD_SECONDS:
                    block_manager.create_block(kind="text")
                    text_button_armed = False

                hovering_code_button = index_pt is not None and point_in_rect(index_pt, BUTTON_CODE_RECT)
                code_button_held = code_button_timer.update(hovering_code_button)
                if not hovering_code_button:
                    code_button_armed = True
                if code_button_armed and code_button_held >= HOVER_HOLD_SECONDS:
                    block_manager.create_block(kind="code")
                    code_button_armed = False

                # --- block hover: select for zoom, or complete a pending link ---
                hovered_block = block_manager.block_at_point(index_pt)
                hovered_block_id = hovered_block["id"] if hovered_block else None
                if hovered_block_id != block_hover_candidate:
                    block_hover_candidate = hovered_block_id
                    block_hover_timer = HoldTimer()
                if hovered_block_id is not None and block_hover_timer.update(True) >= HOVER_HOLD_SECONDS:
                    if linking_from is not None and hovered_block_id != linking_from:
                        block_manager.link(linking_from, hovered_block_id)
                        linking_from = None
                    elif linking_from is None:
                        selected_block_id = hovered_block_id
                        selected_index = None

                # --- circle gesture: marks the circled block as a pending link source ---
                circle_center = circle_detector.update(index_pt)
                if circle_center is not None:
                    circled = block_manager.block_at_point(circle_center)
                    if circled is not None:
                        linking_from = circled["id"]
                        linking_from_time = time.time()
                if linking_from is not None and time.time() - linking_from_time > LINK_TIMEOUT_SECONDS:
                    linking_from = None

                # --- drag blocks around, drop on the trash (held briefly) to delete ---
                deleted_id, trash_progress = block_manager.update_drag(pinch_point, is_pinching)
                if deleted_id is not None:
                    if deleted_id == selected_block_id:
                        selected_block_id = None
                    if deleted_id == linking_from:
                        linking_from = None

                block_manager.draw(frame, hovering_text_button, hovering_code_button,
                                    selected_block_id, linking_from, trash_progress)

                if linking_from is not None:
                    cv2.putText(frame, "Mode liaison : pointez un 2e bloc", (36, CORNER_H - 38),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

                # --- spread-to-fullscreen, for whichever kind is selected ---
                if selected_index is not None:
                    big = cv2.resize(gallery[selected_index]["full"], (CORNER_W - 20, CORNER_H - 20))
                    frame[10:10 + big.shape[0], 10:10 + big.shape[1]] = big
                    cv2.rectangle(frame, (10, 10), (10 + big.shape[1], 10 + big.shape[0]), (0, 255, 255), 2)

                if selected_index is not None or selected_block_id is not None:
                    is_spread = pinch_dist is not None and pinch_dist > SPREAD_THRESHOLD_PX
                    if spread_timer.update(is_spread) >= SPREAD_HOLD_SECONDS and hwnd is not None:
                        if selected_block_id is not None:
                            enter_fullscreen("block", selected_block_id)
                        else:
                            enter_fullscreen("photo")
                else:
                    spread_timer.update(False)

                if fist_armed and fist_held > 0:
                    pct = min(fist_held / FIST_HOLD_SECONDS, 1.0)
                    cv2.rectangle(frame, (10, CORNER_H - 20), (10 + int(100 * pct), CORNER_H - 12), (0, 255, 0), -1)

            elif fullscreen_kind == "photo":
                screen_w, screen_h = screen_size()
                frame = cv2.resize(gallery[selected_index]["full"], (screen_w, screen_h))

                preview_w, preview_h = 220, 160
                preview = cv2.resize(raw_frame, (preview_w, preview_h))
                px, py = 20, screen_h - preview_h - 20
                frame[py:py + preview_h, px:px + preview_w] = preview
                cv2.rectangle(frame, (px, py), (px + preview_w, py + preview_h), (0, 255, 255), 2)
                cv2.putText(frame, "pincez pour revenir", (px, py - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                is_pinching = pinch_dist is not None and pinch_dist < PINCH_THRESHOLD_PX
                if pinch_timer.update(is_pinching) >= PINCH_HOLD_SECONDS and hwnd is not None:
                    return_to_corner()

            else:  # fullscreen_kind == "block"
                screen_w, screen_h = screen_size()
                frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
                block = block_manager.get(fullscreen_block_id)

                if block is None:
                    return_to_corner()
                else:
                    arrow_hover = False
                    arrow_rect = None
                    if hand is not None:
                        ix, iy = hand.point(INDEX_TIP)
                        raw_pt = map_to_screen(ix, iy, native_w, native_h, screen_w, screen_h)
                        if smoothed_index_pt is None:
                            smoothed_index_pt = raw_pt
                        else:
                            alpha = 0.35
                            smoothed_index_pt = (
                                int(smoothed_index_pt[0] * (1 - alpha) + raw_pt[0] * alpha),
                                int(smoothed_index_pt[1] * (1 - alpha) + raw_pt[1] * alpha),
                            )
                        index_pt_full = smoothed_index_pt
                    else:
                        smoothed_index_pt = None
                        index_pt_full = None

                    # --- code blocks: closed fist, held, runs the typed code ---
                    run_progress = 0.0
                    if block["kind"] == "code":
                        is_fist = hand is not None and hand.is_fist()
                        run_held = run_timer.update(is_fist)
                        if not is_fist:
                            run_armed = True
                        if run_armed and run_held >= FIST_HOLD_SECONDS:
                            block["output"] = run_code(block["text"])
                            run_armed = False
                        run_progress = min(run_held / FIST_HOLD_SECONDS, 1.0) if run_armed else 0.0

                    arrow_rect = block_manager.draw_fullscreen(frame, block, hovering_arrow=False, run_progress=run_progress)
                    if arrow_rect is not None and index_pt_full is not None:
                        arrow_hover = point_in_rect(index_pt_full, arrow_rect)
                        if arrow_hover:
                            # redraw highlighted now that we know the hover state
                            frame[:] = 0
                            arrow_rect = block_manager.draw_fullscreen(frame, block, hovering_arrow=True, run_progress=run_progress)

                    if index_pt_full is not None:
                        cv2.circle(frame, index_pt_full, 10, (0, 255, 255), -1)
                        cv2.circle(frame, index_pt_full, 10, (255, 255, 255), 2)

                    if arrow_hover and arrow_hover_timer.update(True) >= HOVER_HOLD_SECONDS:
                        fullscreen_block_id = block["linked_to"]
                        selected_block_id = fullscreen_block_id
                        arrow_hover_timer = HoldTimer()
                        run_timer = HoldTimer()
                        run_armed = True
                    elif not arrow_hover:
                        arrow_hover_timer.update(False)

                    preview_w, preview_h = 220, 160
                    preview = cv2.resize(raw_frame, (preview_w, preview_h))
                    px, py = 20, screen_h - preview_h - 20
                    frame[py:py + preview_h, px:px + preview_w] = preview
                    cv2.rectangle(frame, (px, py), (px + preview_w, py + preview_h), (0, 255, 255), 2)
                    hint = ("tapez du code -- poing ferme pour executer -- Echap ou pincez pour revenir"
                            if block["kind"] == "code" else
                            "tapez du texte -- Echap ou pincez pour revenir")
                    cv2.putText(frame, hint, (px, py - 12),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                    is_pinching = pinch_dist is not None and pinch_dist < PINCH_THRESHOLD_PX
                    if pinch_timer.update(is_pinching) >= PINCH_HOLD_SECONDS and hwnd is not None:
                        return_to_corner()

            cv2.imshow(WINDOW_TITLE, frame)

            if hwnd is None:
                hwnd = pin_to_corner(WINDOW_TITLE, CORNER_W, CORNER_H, corner="bottom-right")

            key = cv2.waitKey(1) & 0xFF
            if typing_mode:
                block = block_manager.get(fullscreen_block_id)
                if key == 27:  # Escape
                    return_to_corner()
                elif block is not None:
                    if key == 8:  # Backspace
                        block["text"] = block["text"][:-1]
                    elif key == 13:  # Enter
                        block["text"] += "\n"
                    elif 32 <= key <= 126:
                        block["text"] += chr(key)
            else:
                if key == ord('q'):
                    break
                if key == ord('c'):
                    gallery.clear()
                    selected_index = None
                    block_manager.blocks.clear()
                    selected_block_id = None
                    linking_from = None
                    if state == STATE_FULLSCREEN and hwnd is not None:
                        return_to_corner()
    finally:
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
