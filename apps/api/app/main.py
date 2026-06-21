from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_validation_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.external.middleware import EXTERNAL_PREFIX, ExternalApiGuard, PathScopedCORS
from app.api.external.problems import (
    ExternalProblem,
    external_problem_handler,
    problem_response,
    request_id_of,
)
from app.api.external.router import router as external_router
from app.api.v1.router import router as api_v1_router
from app.core.errors import (
    approval_conflict_handler,
    conflict_handler,
    server_error_handler,
    unprocessable_handler,
)
from app.core.exceptions import (
    ApprovalApplyError,
    ApprovalConflictError,
    ConflictError,
    PolicyError,
    SecretDetectedError,
)
from app.core.security import LOCAL_UI_ORIGINS
from app.fsmemory.path_safety import PathSafetyError


def _is_external(request: Request) -> bool:
    return request.url.path.startswith(EXTERNAL_PREFIX)


async def _external_aware_validation_handler(request: Request, exc: RequestValidationError):
    """External path/query validation → problem+json; internal keeps default shape."""
    if _is_external(request):
        fields = sorted(
            {".".join(str(p) for p in e["loc"][1:]) or "request" for e in exc.errors()}
        )
        return problem_response(
            422,
            "validation_error",
            "Unprocessable Entity",
            f"invalid request parameter(s): {', '.join(fields)}",
            request_id_of(request),
        )
    return await default_validation_handler(request, exc)


_HTTP_SLUGS = {404: "not_found", 405: "method_not_allowed", 403: "forbidden"}
_HTTP_TITLES = {
    404: "Not Found",
    405: "Method Not Allowed",
    403: "Forbidden",
}


async def _external_aware_http_handler(request: Request, exc: StarletteHTTPException):
    """External routing/method errors → problem+json; internal keeps {"detail"}."""
    if _is_external(request):
        slug = _HTTP_SLUGS.get(exc.status_code, "error")
        title = _HTTP_TITLES.get(exc.status_code, "Error")
        detail = exc.detail if isinstance(exc.detail, str) else title
        return problem_response(exc.status_code, slug, title, detail, request_id_of(request))
    return await default_http_exception_handler(request, exc)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentBoard API",
        version="0.2.0",
        description="Local-first AI project cockpit — API",
    )

    # CORS for the local UI ONLY, restricted to the known local origins (shared with
    # the local control-token check). The external API surface (/api/external/) gets
    # NO CORS — PathScopedCORS bypasses it, and ExternalApiGuard enforces the host
    # allowlist + cookie rejection + body cap before routing.
    app.add_middleware(
        PathScopedCORS,
        allow_origins=list(LOCAL_UI_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ExternalApiGuard)

    # Internal domain-exception handlers (unchanged {"detail"} shape).
    app.add_exception_handler(ConflictError, conflict_handler)
    app.add_exception_handler(PathSafetyError, unprocessable_handler)
    app.add_exception_handler(ApprovalConflictError, approval_conflict_handler)
    app.add_exception_handler(PolicyError, unprocessable_handler)
    app.add_exception_handler(SecretDetectedError, unprocessable_handler)
    app.add_exception_handler(ApprovalApplyError, server_error_handler)

    # External surface: RFC 9457 problem+json (scoped to /api/external/ by path).
    app.add_exception_handler(ExternalProblem, external_problem_handler)
    app.add_exception_handler(RequestValidationError, _external_aware_validation_handler)
    app.add_exception_handler(StarletteHTTPException, _external_aware_http_handler)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(external_router, prefix="/api/external/v1", tags=["external"])

    return app


app = create_app()
