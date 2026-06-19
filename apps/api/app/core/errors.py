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
