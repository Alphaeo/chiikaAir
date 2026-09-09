"""Light exponential-moving-average smoothing for hand-derived points.

Raw fingertip positions jitter a few pixels frame to frame even from a
steady hand -- MediaPipe's own tracking noise. Smoothing it out makes
cursors, drags and hover targets feel steadier without adding
noticeable input lag (an EMA reacts within a handful of frames).
"""


class PointSmoother:
    def __init__(self, alpha: float = 0.35):
        """`alpha` is how much each new sample counts, 0..1 -- higher
        tracks faster but jitters more, lower is smoother but laggier."""
        self._alpha = alpha
        self._value = None

    def update(self, point):
        """Feed the current raw point (or None if not tracked this
        frame -- resets the filter so it doesn't ease in from a stale
        position once the hand reappears). Returns the smoothed point,
        or None."""
        if point is None:
            self._value = None
            return None
        if self._value is None:
            self._value = point
        else:
            a = self._alpha
            self._value = (
                self._value[0] * (1 - a) + point[0] * a,
                self._value[1] * (1 - a) + point[1] * a,
            )
        return (int(self._value[0]), int(self._value[1]))
