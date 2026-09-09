"""Pinch-and-drag demo: pinch thumb + index finger to grab a virtual
object on screen and move it around, like in those Instagram CV reels.

Controls:
  q       quit
  r       reset object to center
"""
import math

import cv2

import theme
from hand_tracker import HandTracker, THUMB_TIP, INDEX_TIP
from smoothing import PointSmoother

# Ratios of hand.scale() (wrist-to-middle-knuckle distance), not raw
# pixels -- so the gesture feels the same whether your hand is close
# to or far from the webcam, instead of only working at one distance.
PINCH_RATIO = 0.35   # thumb+index closer than this fraction of hand size = pinch
GRAB_RATIO = 0.55    # how close the pinch must be to the object to grab it
OBJECT_RADIUS_PX = 45


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    tracker = HandTracker(num_hands=1)
    smoother = PointSmoother()

    obj_pos = None  # set once we know the frame size
    dragging = False

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)  # mirror, feels natural
            height, width = frame.shape[:2]

            if obj_pos is None:
                obj_pos = [width // 2, height // 2]

            hands = tracker.process(frame)

            raw_pinch_point = None
            is_pinching = False

            if hands:
                hand = hands[0]
                thumb = hand.point(THUMB_TIP)
                index = hand.point(INDEX_TIP)
                scale = hand.scale()
                raw_pinch_point = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                is_pinching = scale > 0 and distance(thumb, index) / scale < PINCH_RATIO

                cv2.circle(frame, thumb, 8, theme.ACCENT, -1, cv2.LINE_AA)
                cv2.circle(frame, index, 8, theme.ACCENT, -1, cv2.LINE_AA)
                cv2.line(frame, thumb, index, theme.ACCENT, 2, cv2.LINE_AA)
            else:
                scale = 0

            pinch_point = smoother.update(raw_pinch_point)

            if is_pinching and pinch_point is not None:
                if not dragging and scale > 0 and distance(pinch_point, obj_pos) / scale < GRAB_RATIO:
                    dragging = True
                if dragging:
                    obj_pos[0], obj_pos[1] = pinch_point
            else:
                dragging = False

            color = theme.SUCCESS if dragging else theme.BLOCK_PALETTE[0]
            cv2.circle(frame, tuple(obj_pos), OBJECT_RADIUS_PX, color, -1, cv2.LINE_AA)
            cv2.circle(frame, tuple(obj_pos), OBJECT_RADIUS_PX, theme.TEXT_PRIMARY, 2, cv2.LINE_AA)

            if pinch_point is not None:
                cv2.circle(frame, pinch_point, 5, theme.DANGER if is_pinching else theme.BORDER, -1, cv2.LINE_AA)

            status = "GRABBED" if dragging else ("PINCH" if is_pinching else "OPEN")
            theme.draw_glass_panel(frame, (10, 10), (170, 50))
            theme.put_text(frame, status, (20, 40), scale=1, color=theme.TEXT_PRIMARY, thickness=2)
            theme.draw_glass_panel(frame, (10, height - 40), (260, height - 10))
            theme.put_text(frame, "q: quit  r: reset", (20, height - 18), scale=0.55, color=theme.TEXT_MUTED)

            cv2.imshow("Pinch & Drag", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            if key == ord('r'):
                obj_pos = [width // 2, height // 2]
                dragging = False
    finally:
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
