"""In-memory brake on password guessing at POST /login.

Failed logins are counted per email and per client IP over a sliding window. Once either
count reaches its limit, further attempts are refused (HTTP 429) without the password
being checked, until the oldest failure in the window ages out. A successful login clears
that email's count, never the IP's, so one valid account cannot reset a spray.

The counts live in this process: a restart forgets them, and several uvicorn workers would
each keep their own (dev.ps1 and the Dockerfile run one).
"""
import math
import threading
import time
from collections import deque

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_EMAIL = 5
# Higher than the email limit: a mosque's Wi-Fi or a phone carrier puts many people
# behind one address.
MAX_FAILURES_PER_IP = 20
# Bounds memory when someone sprays many emails or addresses.
_MAX_KEYS = 50_000

_lock = threading.Lock()
_failures: dict[str, deque[float]] = {}


def _limits(email: str, ip: str) -> tuple[tuple[str, int], ...]:
    return ((f"email:{email}", MAX_FAILURES_PER_EMAIL), (f"ip:{ip}", MAX_FAILURES_PER_IP))


def _recent(key: str, now: float) -> deque[float] | None:
    """The key's failures still inside the window, dropping the expired ones."""
    times = _failures.get(key)
    if times is None:
        return None
    while times and now - times[0] >= WINDOW_SECONDS:
        times.popleft()
    if not times:
        del _failures[key]
        return None
    return times


def retry_after(email: str, ip: str) -> int:
    """Seconds until this email/IP may try again; 0 when it may try now."""
    now = time.monotonic()
    wait = 0.0
    with _lock:
        for key, limit in _limits(email, ip):
            times = _recent(key, now)
            if times is not None and len(times) >= limit:
                # Each deque holds at most `limit` entries, so the oldest one decides.
                wait = max(wait, times[0] + WINDOW_SECONDS - now)
    return math.ceil(wait)


def record_failure(email: str, ip: str) -> None:
    now = time.monotonic()
    with _lock:
        for key, limit in _limits(email, ip):
            times = _recent(key, now)
            if times is None:
                times = _failures[key] = deque(maxlen=limit)
            times.append(now)
        if len(_failures) > _MAX_KEYS:
            for key in list(_failures):
                _recent(key, now)
            # Still too many live keys: forget the oldest-created ones.
            for key in list(_failures)[: max(0, len(_failures) - _MAX_KEYS)]:
                del _failures[key]


def record_success(email: str) -> None:
    with _lock:
        _failures.pop(f"email:{email}", None)
