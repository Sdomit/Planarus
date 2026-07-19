import logging

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
from app.mcp.http_transport import MOUNT_PATH, make_mcp_mount, mcp_lifespan
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
from app.core.config import settings
from app.core.security import allowed_ui_origins
from app.fsmemory.path_safety import PathSafetyError

_log = logging.getLogger("approvo")


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
    # Phase 11.0 fail-closed precondition (D25): LAN mode widens the app-wide
    # Host allowlist beyond loopback, and the local control token is explicitly
    # not an identity — refuse to start without real per-user auth.
    if settings.lan_mode_enabled and not settings.auth_enabled:
        raise RuntimeError(
            "AGENTBOARD_LAN_MODE_ENABLED requires AGENTBOARD_AUTH_ENABLED=true "
            "(D25): LAN mode without per-user auth would expose the whole "
            "database to the local network. Refusing to start."
        )
    if settings.lan_mode_enabled:
        lan_hosts = ", ".join(
            h.strip() for h in settings.lan_allowed_hosts.split(",") if h.strip()
        )
        _log.warning(
            "LAN team mode ACTIVE — accepting requests for LAN host(s): %s. "
            "Traffic is plain HTTP: UNENCRYPTED on your local network (D26). "
            "The server socket still binds only where you point uvicorn "
            "(e.g. --host 0.0.0.0 to actually listen on the LAN).",
            lan_hosts or "(none configured — set AGENTBOARD_LAN_ALLOWED_HOSTS)",
        )
        # P11.3: prime the middleware's process-local mirror of the LAN DB
        # switch so a switch left off survives a restart. Best-effort: on a
        # fresh/unmigrated DB the mirror stays unloaded and the env ceiling is
        # the (correct) fallback until the first settings write.
        try:
            from sqlmodel import Session as _Session

            from app.db.session import engine as _engine
            from app.services.settings_service import refresh_lan_switch

            with _Session(_engine) as _s:
                refresh_lan_switch(_s)
        except Exception:  # noqa: BLE001 — env-ceiling fallback is fail-safe
            pass

    app = FastAPI(
        title="Approvo API",
        version="0.2.0",
        description="Local-first AI project cockpit — API",
        lifespan=mcp_lifespan,
    )

    # CORS for the local UI ONLY, restricted to the known local origins (shared with
    # the local control-token check). The external API surface (/api/external/) gets
    # NO CORS — PathScopedCORS bypasses it, and ExternalApiGuard enforces the host
    # allowlist + cookie rejection + body cap before routing.
    app.add_middleware(
        PathScopedCORS,
        allow_origins=list(allowed_ui_origins()),
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
    # P17.4: remote MCP over Streamable HTTP, mounted under the external surface so
    # ExternalApiGuard's ceiling (disabled-by-default, Host allowlist, body cap)
    # applies; agbk_-authenticated and scope-gated inside (D39).
    app.mount(MOUNT_PATH, make_mcp_mount(app))

    return app


app = create_app()
