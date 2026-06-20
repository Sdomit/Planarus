"""Approximate, deterministic token budgeting for context packs.

No external tokenizer is used — `app.core.utils.estimate_tokens` is a documented
chars/4 heuristic and every value is labelled approximate. This module defines
the budget presets, the absolute hard cap, and the deterministic order in which
optional sources are trimmed when a pack exceeds its soft budget.
"""
from __future__ import annotations

# Soft target budgets per preset (approximate tokens). These are targets, not
# hard limits: a pack may slightly exceed its preset after all trims are applied,
# in which case the user gets a visible "over budget" warning.
BUDGET_PRESETS: dict[str, int] = {
    "small": 8_000,
    "medium": 24_000,
    "large": 80_000,
}
DEFAULT_BUDGET_PRESET = "medium"

# Absolute ceilings enforced BEFORE rendering, regardless of preset. A selection
# whose raw assembled size exceeds either ceiling is rejected (HTTP 422) so the
# generator never builds a multi-hundred-KB pack.
HARD_CAP_TOKENS = 200_000
HARD_CAP_CHARS = 800_000

# Deterministic trim order. When the assembled pack exceeds the soft budget,
# these optional/derived groups are removed (or, for docs, truncated then
# dropped) in exactly this sequence. Baseline sources — project summary, agent
# instructions, task objective, constraints, verification, finish format, and the
# core structured state (active tasks, open blockers, open risks, recent
# decisions, phases/stages) — are NEVER trimmed. Pinned sources are trimmed last.
TRIM_AUDIT = "audit"  # 1. debug-only audit metadata slice
TRIM_TASKS_DONE = "tasks_done"  # 2. done/backlog collapse already a count -> drop it
TRIM_RISKS_CLOSED = "risks_closed"  # 3. closed risks + resolved blockers
TRIM_DECISIONS_EXTRA = "decisions_extra"  # 4. decisions beyond the recent default
TRIM_DOC_TRUNCATE = "doc_truncate"  # 5. truncate doc excerpts at heading boundaries
TRIM_DOC_DROP = "doc_drop"  # 6. drop lowest-ranked optional docs
# 7. pinned sources are only trimmed as a last resort (handled separately).

TRIM_ORDER: tuple[str, ...] = (
    TRIM_AUDIT,
    TRIM_TASKS_DONE,
    TRIM_RISKS_CLOSED,
    TRIM_DECISIONS_EXTRA,
    TRIM_DOC_TRUNCATE,
    TRIM_DOC_DROP,
)

# When doc truncation is triggered, each selected doc excerpt is capped to this
# many characters (cut at the nearest heading boundary). A fixed cap keeps
# trimming deterministic and golden-testable.
DOC_TRUNCATE_CHARS = 1_200


def is_valid_budget(preset: str) -> bool:
    return preset in BUDGET_PRESETS


def budget_tokens(preset: str) -> int:
    """Soft token target for a preset. Caller must validate membership first."""
    return BUDGET_PRESETS[preset]
