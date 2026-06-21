"""RFC 9457 ``application/problem+json`` for the external API ONLY.

Internal ``/api/v1`` endpoints keep their ``{"detail": ...}`` shape (Phase 7A/7C0)
— this module is scoped to the external surface. Problem bodies carry only safe
fields and never leak tracebacks, SQL, file paths, tokens, key material, or
secrets. ``instance`` is the per-request id (never a filesystem path).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

PROBLEM_TYPE_BASE = "https://agentboard.app/problems/"
PROBLEM_MEDIA_TYPE = "application/problem+json"
REQUEST_ID_HEADER = "X-Request-Id"


class ExternalProblem(Exception):
    """Raised inside external routes/dependencies; mapped to problem+json.

    ``detail`` must already be safe (no secrets/paths/SQL/tracebacks).
    """

    def __init__(
        self,
        status: int,
        slug: str,
        title: str,
        detail: str,
        *,
        retry_after: Optional[int] = None,
    ) -> None:
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(f"{status} {slug}: {detail}")


def problem_body(status: int, slug: str, title: str, detail: str, instance: str) -> dict:
    return {
        "type": f"{PROBLEM_TYPE_BASE}{slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }


def problem_response(
    status: int,
    slug: str,
    title: str,
    detail: str,
    request_id: str,
    *,
    retry_after: Optional[int] = None,
) -> JSONResponse:
    headers: dict[str, str] = {REQUEST_ID_HEADER: request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(int(retry_after))
    return JSONResponse(
        status_code=status,
        content=problem_body(status, slug, title, detail, request_id),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


async def external_problem_handler(request: Request, exc: ExternalProblem) -> JSONResponse:
    return problem_response(
        exc.status,
        exc.slug,
        exc.title,
        exc.detail,
        request_id_of(request),
        retry_after=exc.retry_after,
    )
