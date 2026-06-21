"""In-process rate limiting for the Phase 7C1 external API.

Local-first only: no Redis, DB table, or external service. Limits reset on
application restart and are a per-process safeguard, not a hosted multi-instance
control. State is bounded (LRU eviction) so a flood of random key ids cannot grow
memory without limit. The clock is injectable so tests can advance time without
sleeping.

Buckets:
  * per-key read    : 60 requests / minute
  * per-key propose : 10 requests / minute
  * global failed-auth (bounded, so random key ids cannot bypass throttling)
  * per-key in-flight concurrency cap
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Optional

WINDOW_SECONDS = 60.0
READ_PER_MIN = 60
PROPOSE_PER_MIN = 10
AUTH_FAIL_PER_MIN = 30
MAX_CONCURRENCY_PER_KEY = 4
MAX_TRACKED_KEYS = 2048


class RateLimiter:
    def __init__(
        self,
        *,
        read_per_min: int = READ_PER_MIN,
        propose_per_min: int = PROPOSE_PER_MIN,
        auth_fail_per_min: int = AUTH_FAIL_PER_MIN,
        max_concurrency: int = MAX_CONCURRENCY_PER_KEY,
        max_keys: int = MAX_TRACKED_KEYS,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.read_per_min = read_per_min
        self.propose_per_min = propose_per_min
        self.auth_fail_per_min = auth_fail_per_min
        self.max_concurrency = max_concurrency
        self.max_keys = max_keys
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._read: "OrderedDict[str, list]" = OrderedDict()
        self._propose: "OrderedDict[str, list]" = OrderedDict()
        self._concurrency: dict[str, int] = {}
        self._auth: list = [0.0, 0]  # [window_start, count]

    # --- fixed-window helper --------------------------------------------------

    def _hit(self, store: "OrderedDict[str, list]", key: str, limit: int) -> Optional[float]:
        """Record one hit; return Retry-After seconds if over the limit, else None."""
        now = self.clock()
        with self._lock:
            entry = store.get(key)
            if entry is None or now - entry[0] >= WINDOW_SECONDS:
                store[key] = [now, 1]
                store.move_to_end(key)
                self._evict(store)
                return None
            start, count = entry
            if count >= limit:
                return max(1.0, WINDOW_SECONDS - (now - start))
            entry[1] += 1
            store.move_to_end(key)
            return None

    def _evict(self, store: "OrderedDict[str, list]") -> None:
        while len(store) > self.max_keys:
            store.popitem(last=False)

    # --- public API -----------------------------------------------------------

    def check_read(self, key_id: str) -> Optional[float]:
        return self._hit(self._read, key_id, self.read_per_min)

    def check_propose(self, key_id: str) -> Optional[float]:
        return self._hit(self._propose, key_id, self.propose_per_min)

    def note_auth_failure(self) -> Optional[float]:
        """Record a failed auth attempt against the bounded global bucket."""
        now = self.clock()
        with self._lock:
            if now - self._auth[0] >= WINDOW_SECONDS:
                self._auth = [now, 1]
                return None
            if self._auth[1] >= self.auth_fail_per_min:
                return max(1.0, WINDOW_SECONDS - (now - self._auth[0]))
            self._auth[1] += 1
            return None

    def acquire(self, key_id: str) -> bool:
        """Take an in-flight slot for ``key_id``; False if the cap is reached."""
        with self._lock:
            n = self._concurrency.get(key_id, 0)
            if n >= self.max_concurrency:
                return False
            self._concurrency[key_id] = n + 1
            return True

    def release(self, key_id: str) -> None:
        with self._lock:
            n = self._concurrency.get(key_id, 0)
            if n <= 1:
                self._concurrency.pop(key_id, None)
            else:
                self._concurrency[key_id] = n - 1

    def reset(self) -> None:
        """Clear all state (test helper / restart simulation)."""
        with self._lock:
            self._read.clear()
            self._propose.clear()
            self._concurrency.clear()
            self._auth = [0.0, 0]


# Process-wide singleton used by the external API dependencies.
limiter = RateLimiter()
