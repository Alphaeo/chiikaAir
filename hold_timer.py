"""Tracks how long a boolean condition has stayed continuously true, on
the wall clock -- so gesture-hold timing doesn't depend on the
webcam's actual frame rate.
"""
import time


class HoldTimer:
    def __init__(self):
        self._since = None

    def update(self, condition: bool) -> float:
        if not condition:
            self._since = None
            return 0.0
        if self._since is None:
            self._since = time.time()
        return time.time() - self._since
