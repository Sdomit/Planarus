"""Unit tests for the approximate token estimator and budget config."""
from app.core.utils import estimate_tokens
from app.prompt import tokens


def test_estimate_tokens_empty_is_zero() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_ceil_div_four() -> None:
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("x" * 400) == 100


def test_estimate_tokens_is_deterministic() -> None:
    text = "The quick brown fox jumps over the lazy dog. " * 10
    assert estimate_tokens(text) == estimate_tokens(text)


def test_budget_presets_present_and_ordered() -> None:
    assert set(tokens.BUDGET_PRESETS) == {"small", "medium", "large"}
    assert tokens.BUDGET_PRESETS["small"] < tokens.BUDGET_PRESETS["medium"]
    assert tokens.BUDGET_PRESETS["medium"] < tokens.BUDGET_PRESETS["large"]
    assert tokens.DEFAULT_BUDGET_PRESET == "medium"


def test_budget_validation_helpers() -> None:
    assert tokens.is_valid_budget("medium")
    assert not tokens.is_valid_budget("enormous")
    assert tokens.budget_tokens("small") == tokens.BUDGET_PRESETS["small"]


def test_hard_cap_is_above_largest_preset() -> None:
    assert tokens.HARD_CAP_TOKENS > tokens.BUDGET_PRESETS["large"]
    assert tokens.HARD_CAP_CHARS >= tokens.HARD_CAP_TOKENS  # chars >= tokens


def test_trim_order_is_deterministic_and_excludes_baseline() -> None:
    # Exact, stable trim sequence; baseline/core sources never appear here.
    assert tokens.TRIM_ORDER == (
        "audit",
        "tasks_done",
        "risks_closed",
        "decisions_extra",
        "doc_truncate",
        "doc_drop",
    )
