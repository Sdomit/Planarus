"""Structured MCP tool errors. Messages are safe: never a traceback, DB URL,
filesystem path, SQL string, secret value, or raw proposal patch."""
from __future__ import annotations

CODE_INVALID = "invalid"
CODE_FORBIDDEN = "forbidden"
CODE_NOT_FOUND = "not_found"
CODE_SECRET = "secret_detected"
CODE_UNAVAILABLE = "unavailable"
CODE_TOO_LARGE = "too_large"
CODE_INTERNAL = "internal"


class MCPToolError(Exception):
    """Raised by tool handlers; mapped to a structured error result by the server."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}
