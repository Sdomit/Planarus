"""Domain-level exceptions and their HTTP translations.

Services raise these framework-agnostic errors; a FastAPI exception handler
(registered in `app.main`) maps them to structured JSON responses so route
handlers stay thin and free of try/except.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class ConflictError(Exception):
    """A write violated a uniqueness constraint (e.g. a duplicate slug)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


async def conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def unprocessable_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map a domain validation error (e.g. an unsafe path) to HTTP 422."""
    detail = getattr(exc, "detail", None) or str(exc)
    return JSONResponse(status_code=422, content={"detail": detail})


# --- Phase 7A: approval engine errors ----------------------------------------


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


async def approval_conflict_handler(
    _request: Request, exc: ApprovalConflictError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def server_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", None) or "internal error"
    return JSONResponse(status_code=500, content={"detail": detail})
