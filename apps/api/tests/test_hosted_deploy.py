"""Phase 10.4 — hosted deploy shape (configurable web origins).

The CORS allowlist and the local control-token Origin check must include hosted
web origins configured via PLANARUS_WEB_ORIGINS, while defaulting to just the
local dev origins (so local behavior is unchanged).
"""
from app.core.config import settings
from app.core.security import LOCAL_UI_ORIGINS, allowed_ui_origins, origin_allowed


def test_default_origins_are_local_only():
    assert allowed_ui_origins() == LOCAL_UI_ORIGINS


def test_web_origins_are_added(monkeypatch):
    monkeypatch.setattr(
        settings, "web_origins", "https://app.example.com, https://planarus.example.com"
    )
    origins = allowed_ui_origins()
    assert "https://app.example.com" in origins
    assert "https://planarus.example.com" in origins
    assert set(LOCAL_UI_ORIGINS).issubset(set(origins))


def test_origin_check_accepts_configured_hosted_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_origins", "https://app.example.com")
    assert origin_allowed("https://app.example.com") is True
    assert origin_allowed("http://evil.example") is False
    # A missing Origin (non-browser client) still passes.
    assert origin_allowed(None) is True


def test_blank_web_origins_ignored(monkeypatch):
    monkeypatch.setattr(settings, "web_origins", " , ,")
    assert allowed_ui_origins() == LOCAL_UI_ORIGINS
