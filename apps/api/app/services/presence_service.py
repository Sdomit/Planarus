"""In-process doc presence + soft-lock (Phase 11.2, D27).

Polling heartbeat over REST — deliberately not WebSocket/CRDT (D27; no realtime
transport exists in the codebase and "X is editing" doesn't justify one).
Presence is ephemeral by definition ("who has this doc open right now"), so
state lives in process memory and a restart correctly clears it; nothing here is
durable or authoritative. Like rate_limit.py this is a per-process safeguard —
a multi-worker deployment would shard presence per worker.
ponytail: in-process dict; move to a small table only if multi-worker ships.

Soft-lock semantics (advisory): a doc's EDITOR is the still-active claimant
whose ``editing`` claim started earliest (first-writer-wins; ties broken by user
id for determinism). Everyone else is told who holds it and the UI drops to
read-only. Dropping to ``viewing``, leaving, or going stale (missed heartbeats)
releases the claim. Nothing here blocks a write — the real write path stays
governed by workspace roles and the approval engine.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional

PRESENCE_TTL_SECONDS = 30.0  # three missed 10s client heartbeats → gone
MAX_TRACKED_DOCS = 2048  # LRU-bounded so doc churn cannot grow memory (rate_limit.py)
MAX_USERS_PER_DOC = 64  # "small team" (D28) with generous headroom

VIEWING = "viewing"
EDITING = "editing"


@dataclass
class _Entry:
    display_name: str
    mode: str
    # Claim ORDER is a store-wide sequence number, not a clock reading: coarse
    # monotonic clocks (Windows ~15.6ms ticks) can stamp two claims identically,
    # which would break first-writer-wins. Staleness still uses the clock.
    claim_seq: Optional[int]  # set while the user claims the edit lock
    last_seen: float


class PresenceStore:
    def __init__(
        self,
        *,
        ttl_seconds: float = PRESENCE_TTL_SECONDS,
        max_docs: int = MAX_TRACKED_DOCS,
        max_users: int = MAX_USERS_PER_DOC,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_docs = max_docs
        self.max_users = max_users
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._docs: "OrderedDict[str, dict[str, _Entry]]" = OrderedDict()
        self._claim_seq = 0

    # --- public API -----------------------------------------------------------

    def heartbeat(self, doc_id: str, user_id: str, display_name: str, mode: str) -> dict:
        """Record one heartbeat and return the doc's current presence view."""
        now = self.clock()
        with self._lock:
            users = self._docs.setdefault(doc_id, {})
            self._docs.move_to_end(doc_id)
            entry = users.get(user_id)
            if entry is None:
                if len(users) >= self.max_users:  # cap: drop the stalest to admit
                    stalest = min(users, key=lambda u: users[u].last_seen)
                    users.pop(stalest)
                users[user_id] = _Entry(
                    display_name=display_name,
                    mode=mode,
                    claim_seq=self._next_seq() if mode == EDITING else None,
                    last_seen=now,
                )
            else:
                if mode == EDITING and entry.mode != EDITING:
                    entry.claim_seq = self._next_seq()  # a fresh claim starts now
                elif mode != EDITING:
                    entry.claim_seq = None  # dropping to viewing releases it
                entry.display_name = display_name
                entry.mode = mode
                entry.last_seen = now
            self._prune(doc_id, now)
            while len(self._docs) > self.max_docs:
                self._docs.popitem(last=False)
            return self._view(doc_id, now)

    def leave(self, doc_id: str, user_id: str) -> None:
        """Explicit release on unmount/blur — faster than waiting out the TTL."""
        with self._lock:
            users = self._docs.get(doc_id)
            if users is not None:
                users.pop(user_id, None)
                if not users:
                    self._docs.pop(doc_id, None)

    def snapshot(self, doc_id: str) -> dict:
        now = self.clock()
        with self._lock:
            self._prune(doc_id, now)
            return self._view(doc_id, now)

    def reset(self) -> None:
        """Clear all state (test helper / restart simulation)."""
        with self._lock:
            self._docs.clear()

    # --- internals (call with the lock held) ----------------------------------

    def _next_seq(self) -> int:
        self._claim_seq += 1
        return self._claim_seq

    def _prune(self, doc_id: str, now: float) -> None:
        users = self._docs.get(doc_id)
        if users is None:
            return
        for uid in [u for u, e in users.items() if now - e.last_seen >= self.ttl_seconds]:
            users.pop(uid)
        if not users:
            self._docs.pop(doc_id, None)

    def _view(self, doc_id: str, now: float) -> dict:
        users = self._docs.get(doc_id, {})
        claims = [
            (e.claim_seq, uid)
            for uid, e in users.items()
            if e.mode == EDITING and e.claim_seq is not None
        ]
        return {
            "entries": [
                {
                    "user_id": uid,
                    "display_name": e.display_name,
                    "mode": e.mode,
                    "idle_seconds": max(0, int(now - e.last_seen)),
                }
                for uid, e in sorted(users.items())
            ],
            "editor_user_id": min(claims)[1] if claims else None,
            "ttl_seconds": int(self.ttl_seconds),
        }


# Process-wide singleton used by the docs presence endpoints.
presence = PresenceStore()
