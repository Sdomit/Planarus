"""Safe filesystem layer for AgentBoard project folders.

This package owns every write into a generated project folder. The DB is the
source of truth; the folder is a portable, derived export. Generated paths come
only from the fixed allowlist in `spec.py` — callers never pass raw filesystem
paths — and every write is containment-checked (`path_safety`) and atomic
(`atomic_io`). See docs/plan/04-filesystem-and-markdown.md.
"""

from app.fsmemory.path_safety import PathSafetyError
from app.fsmemory.regenerator import RegenReport, regenerate

__all__ = ["PathSafetyError", "RegenReport", "regenerate"]
