"""Static, versioned built-in prompt profiles (Phase 6A).

Profiles are reviewed Python code, NOT database rows. They carry the security-
critical agent instructions, safety requirements, and output-format scaffolding
for each kind of task. Keeping them in versioned code means they are diffable,
cache-stable across runs, and cannot be mutated through any AI surface. The
`PromptTemplate` DB entity (user-authored templates) is intentionally deferred to
a later phase.

The `target_tool` only changes model-specific framing — it never changes which
canonical data sources are selected.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Concrete target tools the generated prompt can be framed for. The enum abstracts
# model framing only; the canonical sources are identical across targets.
TARGET_TOOLS: tuple[str, ...] = (
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "codex",
    "cursor",
)

_FINISH_FORMAT: tuple[str, ...] = (
    "1. What changed",
    "2. Files touched",
    "3. Validation performed",
    "4. Risks / open questions",
    "5. Exact next step",
)


@dataclass(frozen=True)
class Profile:
    key: str
    version: int
    label: str
    description: str
    default_target: str
    include_git_checklist: bool
    agent_instructions: tuple[str, ...]
    output_format: tuple[str, ...]
    verification: tuple[str, ...]
    # Optional sources this profile suggests turning on by default in the UI.
    # The service still requires explicit selection flags; this is a hint only.
    suggested_optional_sources: tuple[str, ...] = field(default_factory=tuple)


_PROFILES: dict[str, Profile] = {
    "plan": Profile(
        key="plan",
        version=1,
        label="Plan",
        description="Produce a scoped implementation plan with acceptance criteria.",
        default_target="claude-opus-4-7",
        include_git_checklist=False,
        agent_instructions=(
            "You are a planning assistant for the project described below.",
            "Produce a concrete, scoped plan for the single task objective in"
            " Section 3. Do not write code or edit files in this task.",
            "State an explicit stop condition. Prefer one task per run.",
            "Point to the referenced context instead of restating it.",
        ),
        output_format=(
            "Return a numbered plan:",
            "1. Goal restated in one line",
            "2. Steps (each: action, files likely touched, risk)",
            "3. Acceptance criteria",
            "4. Open questions",
        ),
        verification=(
            "Plan is reviewable, scoped to the stated objective, and names"
            " acceptance criteria before any implementation begins.",
        ),
    ),
    "build": Profile(
        key="build",
        version=1,
        label="Build",
        description="Implement one task within an explicit file scope.",
        default_target="claude-sonnet-4-6",
        include_git_checklist=True,
        agent_instructions=(
            "You are an implementation assistant. Implement the single task"
            " objective in Section 3 — one task, explicit stop condition.",
            "Touch only paths permitted by the constraints in Section 8; never"
            " touch forbidden paths.",
            "Produce a short plan before editing more than one file.",
            "Keep any project write proposed through an AI surface approval-gated.",
        ),
        output_format=(
            "Return the finish format below, plus a concise diff summary.",
            *(f"  {line}" for line in _FINISH_FORMAT),
        ),
        verification=(
            "Run the project's tests/lint before declaring done.",
            "No forbidden paths touched; no new un-gated AI write paths added.",
        ),
    ),
    "review": Profile(
        key="review",
        version=1,
        label="Review",
        description="Review a change for correctness and safety.",
        default_target="claude-opus-4-7",
        include_git_checklist=False,
        agent_instructions=(
            "You are a code/plan reviewer. Review against the objective in"
            " Section 3 using the project context as reference.",
            "Be read-mostly: identify issues and cite concrete evidence; do not"
            " silently rewrite. Propose fixes, do not apply them.",
        ),
        output_format=(
            "Return a findings table: severity | file/area | issue | suggested fix.",
            "End with an overall risk assessment (low/medium/high) and rationale.",
        ),
        verification=(
            "Every finding cites specific evidence from the change or context.",
        ),
    ),
    "debug": Profile(
        key="debug",
        version=1,
        label="Debug",
        description="Isolate and minimally fix a failure.",
        default_target="claude-sonnet-4-6",
        include_git_checklist=True,
        agent_instructions=(
            "You are a debugging assistant. Isolate the failure described in"
            " Section 3 using the project context as reference.",
            "Reproduce first, then propose the smallest change that fixes the"
            " root cause. Avoid unrelated refactors.",
        ),
        output_format=(
            "Return: hypothesis -> checks performed -> root cause -> minimal fix.",
            "Then the finish format below.",
            *(f"  {line}" for line in _FINISH_FORMAT),
        ),
        verification=(
            "The fix is minimal, targets the root cause, and is verified by a"
            " concrete reproduction/check.",
        ),
        suggested_optional_sources=("audit_recent",),
    ),
    "git_safety_review": Profile(
        key="git_safety_review",
        version=1,
        label="Git safety review",
        description="Verify Git hygiene with read-only commands only.",
        default_target="claude-opus-4-7",
        include_git_checklist=True,
        agent_instructions=(
            "You are a Git-safety reviewer. Using ONLY read-only Git commands,"
            " confirm the working state is understood before any change.",
            "Never propose or run a Git mutation (no commit/push/branch/reset).",
            "Surface anything that touches forbidden paths or secrets.",
        ),
        output_format=(
            "Return the Git safety checklist results, then a short risk callout.",
        ),
        verification=(
            "Only read-only Git commands were used; no mutation was suggested.",
        ),
    ),
    "documentation_update": Profile(
        key="documentation_update",
        version=1,
        label="Documentation update",
        description="Update a selected document to match reality.",
        default_target="claude-sonnet-4-6",
        include_git_checklist=False,
        agent_instructions=(
            "You are a documentation assistant. Update the selected document(s)"
            " (Section 7) to match the project state in Section 6.",
            "Stay within the selected document's scope. Do not invent facts; the"
            " canonical document lives in Planarus, not in this prompt.",
        ),
        output_format=(
            "Return the proposed document edits as Markdown, clearly scoped to the"
            " selected document(s).",
        ),
        verification=(
            "Edits are limited to the selected document(s) and are grounded in the"
            " provided project context.",
        ),
    ),
}

# Stable display order for the profiles list endpoint.
PROFILE_ORDER: tuple[str, ...] = (
    "plan",
    "build",
    "review",
    "debug",
    "git_safety_review",
    "documentation_update",
)


def is_valid_profile(key: str) -> bool:
    return key in _PROFILES


def is_valid_target(target: str) -> bool:
    return target in TARGET_TOOLS


def get_profile(key: str) -> Profile:
    """Return the profile for `key`. Caller must validate membership first."""
    return _PROFILES[key]


def all_profiles() -> list[Profile]:
    return [_PROFILES[k] for k in PROFILE_ORDER]
