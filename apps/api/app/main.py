from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.errors import ConflictError, conflict_handler


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentBoard API",
        version="0.2.0",
        description="Local-first AI project cockpit — API",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ConflictError, conflict_handler)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
