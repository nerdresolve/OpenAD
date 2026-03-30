"""
rate_limiter.py — In-memory IP-based sliding window rate limiter.

Tracks request timestamps per IP address and rejects requests that exceed
the configured threshold within the rolling time window.
Thread-safe via threading.Lock.
"""
import time
from collections import defaultdict
from threading import Lock

from app.config import settings


class RateLimiter:
    """Sliding window rate limiter keyed by client IP address."""

    def __init__(
        self,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
    ):
        self._max = max_attempts or settings.RATE_LIMIT_MAX
        self._window = window_seconds or settings.RATE_LIMIT_WINDOW
        self._log: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, ip: str) -> bool:
        """Return True if the IP is within the allowed rate, False otherwise."""
        now = time.monotonic()
        with self._lock:
            self._log[ip] = [t for t in self._log[ip] if now - t < self._window]
            if len(self._log[ip]) >= self._max:
                return False
            self._log[ip].append(now)
            return True

    def remaining(self, ip: str) -> int:
        """Return the number of remaining allowed attempts for the given IP."""
        now = time.monotonic()
        with self._lock:
            self._log[ip] = [t for t in self._log[ip] if now - t < self._window]
            return max(0, self._max - len(self._log[ip]))

    def purge_expired(self) -> None:
        """Remove all expired entries to prevent unbounded memory growth."""
        now = time.monotonic()
        with self._lock:
            stale = [
                ip for ip, ts in self._log.items()
                if not any(now - t < self._window for t in ts)
            ]
            for ip in stale:
                del self._log[ip]


rate_limiter = RateLimiter()
