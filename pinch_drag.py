"""Pinch-and-drag demo: pinch thumb + index finger to grab a virtual
object on screen and move it around, like in those Instagram CV reels.

Controls:
  q       quit
  r       reset object to center
"""
import math

import cv2

from hand_tracker import HandTracker, THUMB_TIP, INDEX_TIP

PINCH_THRESHOLD_PX = 40   # distance below which thumb+index counts as a pinch
GRAB_RADIUS_PX = 60       # how close the pinch must be to the object to grab it
OBJECT_RADIUS_PX = 45


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    tracker = HandTracker(num_hands=1)

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

            pinch_point = None
            is_pinching = False

            if hands:
                hand = hands[0]
                thumb = hand.point(THUMB_TIP)
                index = hand.point(INDEX_TIP)
                pinch_point = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                is_pinching = distance(thumb, index) < PINCH_THRESHOLD_PX

                cv2.circle(frame, thumb, 8, (0, 255, 255), -1)
                cv2.circle(frame, index, 8, (0, 255, 255), -1)
                cv2.line(frame, thumb, index, (0, 255, 255), 2)

            if is_pinching and pinch_point is not None:
                if not dragging and distance(pinch_point, obj_pos) < GRAB_RADIUS_PX:
                    dragging = True
                if dragging:
                    obj_pos[0], obj_pos[1] = pinch_point
            else:
                dragging = False

            color = (60, 220, 255) if dragging else (255, 180, 60)
            cv2.circle(frame, tuple(obj_pos), OBJECT_RADIUS_PX, color, -1)
            cv2.circle(frame, tuple(obj_pos), OBJECT_RADIUS_PX, (255, 255, 255), 2)

            if pinch_point is not None:
                cv2.circle(frame, pinch_point, 5, (0, 0, 255) if is_pinching else (200, 200, 200), -1)

            status = "GRABBED" if dragging else ("PINCH" if is_pinching else "OPEN")
            cv2.putText(frame, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(frame, "q: quit  r: reset", (20, height - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

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
