"""Fixed specification of a generated project folder.

Every generated path is derived from these tables. Callers never supply raw
filesystem paths — this is the allowlist the safety layer enforces, so a bug or
a malicious value can never widen the write surface beyond `context/<FILE>` and
the reserved working directories.
"""
from __future__ import annotations

from dataclasses import dataclass

CONTEXT_DIR = "context"
AGENTBOARD_DIR = ".agentboard"
AUDIT_LOG_RELPATH = f"{AGENTBOARD_DIR}/audit-log.jsonl"


@dataclass(frozen=True)
class ContextFileSpec:
    """One generated Markdown file: its filename and its ContextFile.kind.

    ``authored=True`` marks a human-maintained file whose renderer only produces
    a starter scaffold (NEXT_STEP/ARCHITECTURE/TEST_PLAN are content-free stubs).
    Regeneration writes the scaffold once when absent, then never overwrites it —
    so hand-written content survives every regen, including the first one after a
    fresh checkout (before any ContextFile row exists). Data-driven files
    (ROADMAP/TASKS/DECISIONS/RISKS/STATUS) stay authored=False and regenerate.
    """

    filename: str
    kind: str
    authored: bool = False

    @property
    def relative_path(self) -> str:
        return f"{CONTEXT_DIR}/{self.filename}"


# Order matches the folder tree in docs/plan/04-filesystem-and-markdown.md.
# `kind` values are the locked 11-value ContextFile enum (03-data-model.md), so
# some kinds repeat — uniqueness is on relative_path, not kind.
CONTEXT_FILES: tuple[ContextFileSpec, ...] = (
    ContextFileSpec("PROJECT.md", "project_context"),
    ContextFileSpec("CONTEXT.md", "project_context"),
    ContextFileSpec("STATUS.md", "project_context"),
    ContextFileSpec("NEXT_STEP.md", "next_step", authored=True),
    ContextFileSpec("ROADMAP.md", "custom"),
    ContextFileSpec("TASKS.md", "custom"),
    ContextFileSpec("DECISIONS.md", "decisions"),
    ContextFileSpec("RISKS.md", "risks"),
    ContextFileSpec("AGENTS.md", "agent_rules"),
    ContextFileSpec("AGENT_RULES.md", "agent_rules", authored=True),
    ContextFileSpec("FILES_ALLOWED.md", "files_allowed"),
    ContextFileSpec("FILES_FORBIDDEN.md", "files_forbidden"),
    ContextFileSpec("ARCHITECTURE.md", "architecture", authored=True),
    ContextFileSpec("TEST_PLAN.md", "test_plan", authored=True),
    ContextFileSpec("PROMPTS.md", "custom"),
    ContextFileSpec("CHANGELOG.md", "changelog"),
)

# Reserved working directories, created empty during provisioning.
RESERVED_DIRS: tuple[str, ...] = (
    "prompts/claude",
    "prompts/codex",
    "prompts/chatgpt",
    "prompts/opencode",
    "prompts/cursor",
    "prompts/shared",
    "docs/product",
    "docs/research",
    "docs/implementation",
    "docs/release",
    "runs",
    "imports/pending",
    "imports/committed",
    "attachments",
    "exports",
)
