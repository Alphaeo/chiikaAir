"""Draggable rounded-rect blocks: created via "+" (text) or "<>" (code)
buttons, moved by pinch-drag (thumb+index, the same mechanic as
pinch_drag.py), deleted by dragging onto a trash button. A text block
holds typed text once zoomed to fullscreen; a code block holds typed
Python and runs it (see code_runner.py) on a fist gesture while
zoomed. Any block can be linked to one other block -- linked pairs are
always shown connected by an arrow in the corner view, and a zoomed
block with a link shows an on-screen arrow to jump straight to it.
"""
import cv2

from hold_timer import HoldTimer

MAX_BLOCKS = 4

BUTTON_MARGIN = 12
BUTTON_SIZE = 40
BUTTON_TEXT_RECT = (BUTTON_MARGIN, BUTTON_MARGIN, BUTTON_MARGIN + BUTTON_SIZE, BUTTON_MARGIN + BUTTON_SIZE)
BUTTON_CODE_RECT = (BUTTON_MARGIN, BUTTON_MARGIN * 2 + BUTTON_SIZE,
                     BUTTON_MARGIN + BUTTON_SIZE, BUTTON_MARGIN * 2 + BUTTON_SIZE * 2)

TRASH_MARGIN = 12
TRASH_SIZE = 40
TRASH_HOLD_SECONDS = 0.4  # dragging onto the trash must be held briefly, so a
                          # block passing over it in transit isn't deleted by accident

BLOCK_W, BLOCK_H = 90, 60
BLOCK_RADIUS = 12
BLOCK_BORDER_COLOR = (255, 255, 255)
BLOCK_GRAB_MARGIN = 10   # grabbing also works just outside the visible edge

SELECTED_BORDER_COLOR = (0, 255, 255)     # cyan: zoom-selected
LINKING_BORDER_COLOR = (255, 0, 255)      # magenta: pending link source
LINK_LINE_COLOR = (220, 220, 220)         # connecting arrow between linked blocks

CODE_BG_COLOR = (30, 30, 30)  # fixed dark gray-black for every code block

# Cycled by a block's creation id (not its list position), so colors stay
# stable per-block and a freed slot doesn't immediately reuse the same hue.
PALETTE = [
    (60, 120, 255),   # orange
    (80, 200, 120),   # green
    (220, 150, 60),   # teal-blue
    (170, 80, 220),   # purple
    (60, 200, 230),   # yellow
    (90, 90, 220),    # red
]

FULLSCREEN_MARGIN = 100
ARROW_W, ARROW_H = 60, 100


def draw_rounded_rect(img, top_left, bottom_right, radius, color, thickness=-1):
    x1, y1 = top_left
    x2, y2 = bottom_right
    radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if thickness < 0:
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
        for cx, cy in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius),
                       (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
            cv2.circle(img, (cx, cy), radius, color, -1)
    else:
        cv2.line(img, (x1 + radius, y1), (x2 - radius, y1), color, thickness)
        cv2.line(img, (x1 + radius, y2), (x2 - radius, y2), color, thickness)
        cv2.line(img, (x1, y1 + radius), (x1, y2 - radius), color, thickness)
        cv2.line(img, (x2, y1 + radius), (x2, y2 - radius), color, thickness)
        cv2.ellipse(img, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness)
        cv2.ellipse(img, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness)
        cv2.ellipse(img, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness)
        cv2.ellipse(img, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness)


def wrap_text(text, font, font_scale, thickness, max_width):
    lines = []
    for raw_line in text.split("\n"):
        if raw_line == "":
            lines.append("")
            continue
        words = raw_line.split(" ")
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            (w, _), _ = cv2.getTextSize(candidate, font, font_scale, thickness)
            if w <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _point_in_rect(point, rect) -> bool:
    x, y = point
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def _expand(rect, margin):
    x1, y1, x2, y2 = rect
    return (x1 - margin, y1 - margin, x2 + margin, y2 + margin)


def _clamp(v, lo, hi):
    return max(lo, min(v, hi))


class BlockManager:
    """Owns the list of on-screen blocks: creation, pinch-and-drag,
    trash deletion, linking, and drawing (corner view + fullscreen
    view). All coordinates are in the caller's display window pixel
    space -- the same space as the frame it draws onto."""

    def __init__(self, bounds_w: int, bounds_h: int):
        self.bounds_w = bounds_w
        self.bounds_h = bounds_h
        self.blocks: list[dict] = []
        self._next_id = 1
        self._dragging_id = None
        self._drag_offset = (0, 0)
        self._trash_timer = HoldTimer()

    @property
    def dragging_id(self):
        return self._dragging_id

    @property
    def trash_rect(self):
        x2 = self.bounds_w - TRASH_MARGIN
        y2 = self.bounds_h - TRASH_MARGIN
        return (x2 - TRASH_SIZE, y2 - TRASH_SIZE, x2, y2)

    def get(self, block_id):
        if block_id is None:
            return None
        return next((b for b in self.blocks if b["id"] == block_id), None)

    def rect_of(self, block) -> tuple[int, int, int, int]:
        return (block["x"], block["y"], block["x"] + block["w"], block["y"] + block["h"])

    def center_of(self, block) -> tuple[int, int]:
        return (block["x"] + block["w"] // 2, block["y"] + block["h"] // 2)

    def block_at_point(self, point):
        if point is None:
            return None
        for block in self.blocks:
            if _point_in_rect(point, self.rect_of(block)):
                return block
        return None

    def create_block(self, kind: str = "text"):
        if len(self.blocks) >= MAX_BLOCKS:
            return None
        n = len(self.blocks)
        x = min(30 + (n * 25) % 200, self.bounds_w - BLOCK_W - 10)
        y = min(70 + (n * 25) % 160, self.bounds_h - BLOCK_H - 10)
        color = CODE_BG_COLOR if kind == "code" else PALETTE[self._next_id % len(PALETTE)]
        block = {
            "id": self._next_id,
            "kind": kind,
            "x": x, "y": y, "w": BLOCK_W, "h": BLOCK_H,
            "color": color,
            "text": "",
            "output": "",
            "linked_to": None,
        }
        self._next_id += 1
        self.blocks.append(block)
        return block["id"]

    def delete(self, block_id) -> None:
        self.blocks = [b for b in self.blocks if b["id"] != block_id]
        for b in self.blocks:
            if b["linked_to"] == block_id:
                b["linked_to"] = None
        if self._dragging_id == block_id:
            self._dragging_id = None

    def link(self, from_id, to_id) -> None:
        block = self.get(from_id)
        if block is not None and to_id in {b["id"] for b in self.blocks}:
            block["linked_to"] = to_id

    def update_drag(self, pinch_point, is_pinching: bool):
        """Call once per frame with the current thumb+index midpoint
        (in this manager's coordinate space) and whether it's pinched.
        Returns (deleted_block_id_or_None, trash_hold_progress 0..1)."""
        if not is_pinching or pinch_point is None:
            self._dragging_id = None
            self._trash_timer.update(False)
            return None, 0.0

        if self._dragging_id is None:
            for block in self.blocks:
                if _point_in_rect(pinch_point, _expand(self.rect_of(block), BLOCK_GRAB_MARGIN)):
                    self._dragging_id = block["id"]
                    self._drag_offset = (pinch_point[0] - block["x"], pinch_point[1] - block["y"])
                    break

        block = self.get(self._dragging_id)
        if block is None:
            self._trash_timer.update(False)
            return None, 0.0

        block["x"] = _clamp(pinch_point[0] - self._drag_offset[0], 0, self.bounds_w - block["w"])
        block["y"] = _clamp(pinch_point[1] - self._drag_offset[1], 0, self.bounds_h - block["h"])

        over_trash = _point_in_rect(pinch_point, self.trash_rect)
        held = self._trash_timer.update(over_trash)
        if held >= TRASH_HOLD_SECONDS:
            deleted_id = self._dragging_id
            self.delete(deleted_id)
            self._trash_timer.update(False)
            return deleted_id, 0.0
        return None, (held / TRASH_HOLD_SECONDS if over_trash else 0.0)

    def draw(self, frame, hovering_text_button: bool, hovering_code_button: bool,
             selected_id=None, linking_from_id=None, trash_progress: float = 0.0) -> None:
        for block in self.blocks:
            top_left = (block["x"], block["y"])
            bottom_right = (block["x"] + block["w"], block["y"] + block["h"])
            draw_rounded_rect(frame, top_left, bottom_right, BLOCK_RADIUS, block["color"], -1)
            if block["id"] == linking_from_id:
                border, thickness = LINKING_BORDER_COLOR, 3
            elif block["id"] == selected_id:
                border, thickness = SELECTED_BORDER_COLOR, 3
            else:
                border, thickness = BLOCK_BORDER_COLOR, 2
            draw_rounded_rect(frame, top_left, bottom_right, BLOCK_RADIUS, border, thickness)

        # permanent connecting arrow for every already-established link
        for block in self.blocks:
            target = self.get(block["linked_to"])
            if target is not None:
                cv2.arrowedLine(frame, self.center_of(block), self.center_of(target),
                                 LINK_LINE_COLOR, 2, tipLength=0.12)

        # "+" (text) button, top-left
        color = (0, 255, 255) if hovering_text_button else (255, 255, 255)
        x1, y1, x2, y2 = BUTTON_TEXT_RECT
        draw_rounded_rect(frame, (x1, y1), (x2, y2), 10, (70, 70, 70), -1)
        draw_rounded_rect(frame, (x1, y1), (x2, y2), 10, color, 2)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.line(frame, (cx - 10, cy), (cx + 10, cy), color, 2)
        cv2.line(frame, (cx, cy - 10), (cx, cy + 10), color, 2)

        # "<>" (code) button, just below it
        ccolor = (0, 255, 255) if hovering_code_button else (255, 255, 255)
        x1, y1, x2, y2 = BUTTON_CODE_RECT
        draw_rounded_rect(frame, (x1, y1), (x2, y2), 10, (70, 70, 70), -1)
        draw_rounded_rect(frame, (x1, y1), (x2, y2), 10, ccolor, 2)
        cv2.putText(frame, "<>", (x1 + 3, y2 - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ccolor, 2, cv2.LINE_AA)

        # trash button, bottom-right -- fills red as a held drag-to-delete progresses
        tx1, ty1, tx2, ty2 = self.trash_rect
        trash_color = (60, 60, 220) if trash_progress > 0 else (90, 90, 90)
        draw_rounded_rect(frame, (tx1, ty1), (tx2, ty2), 8, (50, 50, 50), -1)
        draw_rounded_rect(frame, (tx1, ty1), (tx2, ty2), 8, trash_color, 2)
        lx1, ly1, lx2, ly2 = tx1 + 8, ty1 + 12, tx2 - 8, ty1 + 16
        cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), trash_color, -1)
        for i in range(3):
            lx = tx1 + 14 + i * 8
            cv2.line(frame, (lx, ty1 + 18), (lx, ty2 - 8), trash_color, 2)
        if trash_progress > 0:
            bar_w = int((tx2 - tx1) * trash_progress)
            cv2.rectangle(frame, (tx1, ty2 + 4), (tx1 + bar_w, ty2 + 8), (60, 60, 220), -1)

    def draw_fullscreen(self, frame, block, hovering_arrow: bool, run_progress: float = 0.0):
        """Draws `block` filling most of `frame`, with its content and
        (if linked) a right-hand navigation arrow. Returns the arrow's
        rect in frame coordinates, or None if this block has no live
        link."""
        h, w = frame.shape[:2]
        x1, y1 = FULLSCREEN_MARGIN, FULLSCREEN_MARGIN
        x2, y2 = w - FULLSCREEN_MARGIN, h - FULLSCREEN_MARGIN
        font = cv2.FONT_HERSHEY_SIMPLEX

        if block["kind"] == "code":
            draw_rounded_rect(frame, (x1, y1), (x2, y2), 30, CODE_BG_COLOR, -1)
            draw_rounded_rect(frame, (x1, y1), (x2, y2), 30, (90, 220, 90), 3)

            split_y = y1 + int((y2 - y1) * 0.6)
            code_scale, code_thickness, line_height = 0.75, 1, 30

            cv2.putText(frame, "CODE -- poing ferme pour executer", (x1 + 30, y1 + 40),
                        font, 0.6, (150, 150, 150), 1, cv2.LINE_AA)
            code_text = block["text"] if block["text"] else "print('hello')"
            lines = wrap_text(code_text, font, code_scale, code_thickness, (x2 - x1) - 60)
            ty = y1 + 80
            for line in lines[: max(1, (split_y - y1 - 90) // line_height)]:
                cv2.putText(frame, line, (x1 + 30, ty), font, code_scale, (140, 255, 140), code_thickness, cv2.LINE_AA)
                ty += line_height

            cv2.line(frame, (x1 + 20, split_y), (x2 - 20, split_y), (90, 90, 90), 1)
            cv2.putText(frame, "SORTIE", (x1 + 30, split_y + 30), font, 0.6, (150, 150, 150), 1, cv2.LINE_AA)
            out_lines = wrap_text(block.get("output", ""), font, code_scale, code_thickness, (x2 - x1) - 60)
            ty = split_y + 60
            for line in out_lines[: max(1, (y2 - split_y - 90) // line_height)]:
                cv2.putText(frame, line, (x1 + 30, ty), font, code_scale, (200, 200, 200), code_thickness, cv2.LINE_AA)
                ty += line_height

            if run_progress > 0:
                bar_w = int((x2 - x1 - 60) * run_progress)
                cv2.rectangle(frame, (x1 + 30, y2 - 20), (x1 + 30 + bar_w, y2 - 12), (90, 220, 90), -1)
        else:
            draw_rounded_rect(frame, (x1, y1), (x2, y2), 40, block["color"], -1)
            draw_rounded_rect(frame, (x1, y1), (x2, y2), 40, (255, 255, 255), 3)

            font_scale, thickness, line_height = 1.1, 2, 42
            text = block["text"] if block["text"] else "..."
            lines = wrap_text(text, font, font_scale, thickness, (x2 - x1) - 80)
            max_lines = max(1, (y2 - y1 - 100) // line_height)
            ty = y1 + 70
            for line in lines[:max_lines]:
                cv2.putText(frame, line, (x1 + 40, ty), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
                ty += line_height

        target = self.get(block["linked_to"])
        if target is None:
            return None

        ax1 = x2 + 20
        ay1 = (h - ARROW_H) // 2
        ax2 = ax1 + ARROW_W
        ay2 = ay1 + ARROW_H
        color = (0, 255, 255) if hovering_arrow else (255, 255, 255)
        cv2.arrowedLine(frame, (ax1, (ay1 + ay2) // 2), (ax2, (ay1 + ay2) // 2), color, 6, tipLength=0.4)
        return (ax1, ay1, ax2, ay2)
