"""Unit tests for best-effort secret detection.

All secret-like values here are FAKE fixtures, never real credentials.
"""
from app.prompt import secrets

# Synthetic, well-known-dummy values only.
_FAKE_AWS = "AKIAIOSFODNN7EXAMPLE"
_FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEFghiJKLmnoPQR"
_FAKE_ASSIGN = "password=hunter2supersecretvalue"
_FAKE_DOTENV = "API_KEY=abcdef123456ZZ"


def test_scan_empty_returns_nothing() -> None:
    assert secrets.scan("", "src") == []


def test_scan_detects_fake_aws_key() -> None:
    findings = secrets.scan(f"key is {_FAKE_AWS}", "src")
    labels = {f.pattern_label for f in findings}
    assert "aws-access-key" in labels


def test_scan_detects_assignment_and_dotenv() -> None:
    labels = {f.pattern_label for f in secrets.scan(_FAKE_ASSIGN, "src")}
    assert "secret-assignment" in labels
    labels2 = {f.pattern_label for f in secrets.scan(_FAKE_DOTENV, "src")}
    assert "dotenv-assignment" in labels2


def test_scan_detects_fake_jwt() -> None:
    labels = {f.pattern_label for f in secrets.scan(_FAKE_JWT, "src")}
    assert "jwt" in labels


def test_findings_never_contain_raw_value() -> None:
    text = f"{_FAKE_AWS} {_FAKE_ASSIGN} {_FAKE_JWT}"
    for f in secrets.scan(text, "src"):
        assert _FAKE_AWS not in f.masked_preview
        assert "hunter2supersecretvalue" not in f.masked_preview
        assert _FAKE_JWT not in f.masked_preview
        # The source ref echoes the label, not the value.
        assert f.source_ref == "src"


def test_mask_keeps_short_prefix_only() -> None:
    masked = secrets.mask("AKIAIOSFODNN7EXAMPLE")
    assert masked.startswith("AKIA")
    assert "IOSFODNN7EXAMPLE" not in masked
    assert "•" in masked


def test_count_aggregates_per_label() -> None:
    findings = secrets.scan(f"{_FAKE_AWS} and {_FAKE_AWS}", "src")
    aws = [f for f in findings if f.pattern_label == "aws-access-key"][0]
    assert aws.count == 2


def test_normal_prose_is_not_flagged_as_high_entropy() -> None:
    findings = secrets.scan(
        "This is an ordinary sentence describing the project plan and goals.",
        "src",
    )
    assert findings == []
