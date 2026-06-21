"""MCP tool input schemas + handlers (pure; no MCP-SDK import)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictArgs(BaseModel):
    """Base for all tool input models: unknown fields are rejected (fail closed)."""

    model_config = ConfigDict(extra="forbid")
