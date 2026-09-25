"""Server-wide rate limits for the free OpenStreetMap services we call.

One limiter per upstream, shared by every request this server handles, so the app as a
whole (not each visitor) stays within the providers' usage policies.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    """Hands out request slots at least `min_interval` seconds apart."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_at = 0.0

    def acquire(self, max_wait: float) -> bool:
        """Reserve the next slot and sleep until it comes.

        Returns False without reserving anything if that slot is more than `max_wait`
        seconds away (the caller should then give up rather than queue forever).
        """
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_at)
            if slot - now > max_wait:
                return False
            self._next_at = slot + self.min_interval
        time.sleep(max(0.0, slot - now))
        return True


# https://dev.overpass-api.de/overpass-doc/en/preface/commons.html — keep it light.
overpass_limiter = RateLimiter(1.0)
# https://operations.osmfoundation.org/policies/nominatim/ — absolute maximum 1 request/second.
nominatim_limiter = RateLimiter(1.0)
