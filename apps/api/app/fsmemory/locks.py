"""Per-project write locks for regeneration.

A single regeneration of a project folder must not interleave with another for
the same root. AgentBoard runs as one local process, so an in-process lock keyed
by the canonical root is sufficient (cross-process file locking is out of scope
for the local-first MVP).
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

_registry_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _key(root: str) -> str:
    return os.path.normcase(os.path.realpath(root))


@contextmanager
def project_lock(root: str) -> Iterator[None]:
    key = _key(root)
    with _registry_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        yield
