"""Framework-neutral domain exceptions.

Services, policy, the approval engine, and the MCP layer raise these. This module
intentionally imports **nothing** framework-specific — no FastAPI/Starlette,
Pydantic, SQLModel/SQLAlchemy, MCP, or any HTTP request/response type — so those
layers stay importable without transitively loading a web framework (Phase 7C0).

The FastAPI exception handlers that translate these into HTTP responses live at
the HTTP boundary in ``app/core/errors.py`` (imported only by ``app/main.py``).
The class meanings and the HTTP status they map to are unchanged from Phase 7A/7B.
"""
from __future__ import annotations


class ConflictError(Exception):
    """A write violated a uniqueness constraint (e.g. a duplicate slug). HTTP 409."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ApprovalConflictError(Exception):
    """An approval action is invalid for the request's current state (HTTP 409).

    Covers replay, wrong-state, expired, stale, and invalidated transitions.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class PolicyError(Exception):
    """A proposal violated the action/field allowlist or a precondition (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class SecretDetectedError(Exception):
    """A proposal payload contained a possible secret and was rejected (HTTP 422).

    The detail is intentionally generic — a raw secret value is NEVER placed in
    the message, response body, logs, or audit record.
    """

    def __init__(
        self, detail: str = "proposal contains a possible secret and was rejected"
    ) -> None:
        self.detail = detail
        super().__init__(detail)


class ApprovalApplyError(Exception):
    """Applying an approved proposal failed unexpectedly (HTTP 500).

    The failure is recorded on the ApprovalRequest (status=failed) before this is
    raised. The detail never contains secret or full-patch content.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
