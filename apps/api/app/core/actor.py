"""Request-scoped actor context (Phase 16.0, D32).

Set once where a session cookie resolves to a ``User`` — the async auth
dependencies (`tenant_user`, `get_current_user`) — and read by
``audit_service.create_audit_event`` so every existing audit call site gains
attribution without a signature change.

Auth off → never set → every audit row keeps ``actor_id=None``, byte-identical
to pre-Phase-16 behavior. Non-HTTP callers (MCP stdio, scripts, tests calling
services directly) never set it either, which is the correct attribution.

The set MUST happen in the request's event-loop task (async dependency), not in
a sync threadpool dependency: `run_in_threadpool` copies the context per call,
so a value set inside one worker thread is invisible to the endpoint's thread.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_current_actor_id: ContextVar[Optional[str]] = ContextVar(
    "current_actor_id", default=None
)


def set_current_actor_id(user_id: Optional[str]) -> None:
    _current_actor_id.set(user_id)


def current_actor_id() -> Optional[str]:
    return _current_actor_id.get()
