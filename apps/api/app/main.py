from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.errors import (
    ApprovalApplyError,
    ApprovalConflictError,
    ConflictError,
    PolicyError,
    SecretDetectedError,
    approval_conflict_handler,
    conflict_handler,
    server_error_handler,
    unprocessable_handler,
)
from app.core.security import LOCAL_UI_ORIGINS
from app.fsmemory.path_safety import PathSafetyError


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentBoard API",
        version="0.2.0",
        description="Local-first AI project cockpit — API",
    )

    # CORS is restricted to the known local UI origins (shared with the local
    # control-token check in app.core.security). Wildcard origins are forbidden.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_UI_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ConflictError, conflict_handler)
    app.add_exception_handler(PathSafetyError, unprocessable_handler)
    app.add_exception_handler(ApprovalConflictError, approval_conflict_handler)
    app.add_exception_handler(PolicyError, unprocessable_handler)
    app.add_exception_handler(SecretDetectedError, unprocessable_handler)
    app.add_exception_handler(ApprovalApplyError, server_error_handler)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
