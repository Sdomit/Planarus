"""FastAPI exception handlers — the HTTP boundary for domain exceptions.

The framework-neutral exception CLASSES live in ``app/core/exceptions.py``; this
module only maps them to HTTP responses and is imported only by ``app/main.py``.
The classes are re-exported here for backward compatibility at the HTTP boundary.
Service / policy / MCP code must import the classes from ``app.core.exceptions``,
never from here, so those layers do not transitively load FastAPI.
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (  # re-exported for the HTTP boundary only
    ApprovalApplyError,
    ApprovalConflictError,
    ConflictError,
    PolicyError,
    SecretDetectedError,
)

__all__ = [
    "ConflictError",
    "ApprovalConflictError",
    "PolicyError",
    "SecretDetectedError",
    "ApprovalApplyError",
    "conflict_handler",
    "unprocessable_handler",
    "approval_conflict_handler",
    "server_error_handler",
]


async def conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def unprocessable_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map a domain validation error (unsafe path, policy/secret rejection) to HTTP 422."""
    detail = getattr(exc, "detail", None) or str(exc)
    return JSONResponse(status_code=422, content={"detail": detail})


async def approval_conflict_handler(
    _request: Request, exc: ApprovalConflictError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def server_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", None) or "internal error"
    return JSONResponse(status_code=500, content={"detail": detail})
