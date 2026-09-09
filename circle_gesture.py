"""Detects a circle traced by a fingertip: a short trail of recent
points that sweeps most of the way around its own centroid and closes
back near where it started.

This is a heuristic, not a trained gesture classifier -- it works well
for a deliberate, reasonably sized circle drawn within ~1s, and may
need its thresholds tuned to taste (too sensitive / not sensitive
enough) once tried live.
"""
import math
import time
from collections import deque

TRAIL_SECONDS = 1.2         # only remember this much recent history
MIN_POINTS = 12             # enough samples to call it deliberate, not jitter
MIN_RADIUS_PX = 18          # ignore tiny wobble as a "circle"
MIN_SWEEP_DEGREES = 300     # must go most of the way around the centroid
MAX_CLOSE_DISTANCE_PX = 40  # start and end must land back near each other


class CircleDetector:
    def __init__(self):
        self._points = deque()  # (x, y, t)

    def update(self, point):
        """Feed the current fingertip position (None if no hand this
        frame). Returns the (x, y) centroid of the traced loop the
        instant a circle is recognized, else None. The trail resets
        after a successful detection."""
        now = time.time()
        while self._points and now - self._points[0][2] > TRAIL_SECONDS:
            self._points.popleft()

        if point is None:
            return None

        self._points.append((point[0], point[1], now))
        if len(self._points) < MIN_POINTS:
            return None

        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)

        radii = [math.hypot(x - cx, y - cy) for x, y in zip(xs, ys)]
        if max(radii) < MIN_RADIUS_PX:
            return None  # too small/flat to be a deliberate circle

        angles = [math.atan2(y - cy, x - cx) for x, y in zip(xs, ys)]
        sweep = 0.0
        for a1, a2 in zip(angles, angles[1:]):
            d = a2 - a1
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            sweep += d
        if abs(math.degrees(sweep)) < MIN_SWEEP_DEGREES:
            return None  # didn't go far enough around

        start_x, start_y, _ = self._points[0]
        end_x, end_y, _ = self._points[-1]
        if math.hypot(end_x - start_x, end_y - start_y) > MAX_CLOSE_DISTANCE_PX:
            return None  # never closed the loop

        self._points.clear()
        return (cx, cy)
