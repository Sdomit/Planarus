import json

import pytest
from app.mcp import capabilities
from app.mcp.capabilities import Capability


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json",
        "[]",
        "123",
        '{"tier":"read"}',  # missing workspace_id/project_ids
        '{"tier":"apply","workspace_id":"w","project_ids":["p"]}',  # bad tier
        '{"tier":"approve","workspace_id":"w","project_ids":["p"]}',
        '{"tier":"read","workspace_id":"","project_ids":["p"]}',  # empty ws
        '{"tier":"read","workspace_id":"w","project_ids":[]}',  # empty projects
        '{"tier":"read","workspace_id":"w","project_ids":[1,2]}',  # non-str ids
    ],
)
def test_default_deny(raw):
    cap = capabilities.parse_capability(raw)
    assert cap.valid is False
    assert cap.project_ids == frozenset()


def test_no_approve_or_apply_tier():
    for tier in ("approve", "apply", "admin", "write"):
        raw = json.dumps({"tier": tier, "workspace_id": "w", "project_ids": ["p"]})
        assert capabilities.parse_capability(raw).valid is False


def test_project_id_cap_of_50():
    pids = [f"p{i}" for i in range(51)]
    raw = json.dumps({"tier": "read", "workspace_id": "w", "project_ids": pids})
    assert capabilities.parse_capability(raw).valid is False
    pids50 = [f"p{i}" for i in range(50)]
    raw50 = json.dumps({"tier": "read", "workspace_id": "w", "project_ids": pids50})
    assert capabilities.parse_capability(raw50).valid is True


def test_oversized_raw_denied():
    raw = json.dumps({"tier": "read", "workspace_id": "w", "project_ids": ["p"], "label": "x" * 9000})
    assert capabilities.parse_capability(raw).valid is False


def test_label_sanitized_into_actor_ref():
    raw = '{"tier":"read","workspace_id":"w","project_ids":["p"],"label":"Bad/Label <script>\\n\\ttabs"}'
    cap = capabilities.parse_capability(raw)
    assert cap.valid
    assert cap.actor_ref.startswith("mcp:")
    for ch in ("/", "<", ">", "\n", "\t"):
        assert ch not in cap.actor_ref


def test_valid_read_and_propose():
    r = capabilities.parse_capability('{"tier":"read","workspace_id":"w","project_ids":["p1","p2"]}')
    assert r.valid and r.tier == "read" and r.project_ids == frozenset({"p1", "p2"})
    p = capabilities.parse_capability('{"tier":"propose","workspace_id":"w","project_ids":["p1"],"label":"cli"}')
    assert p.valid and p.tier == "propose" and p.actor_ref == "mcp:cli"


def test_allows_project():
    cap = Capability(tier="read", workspace_id="w", project_ids=frozenset({"p1"}), label="l")
    assert cap.allows_project("p1") is True
    assert cap.allows_project("p2") is False
    assert capabilities.DENY.allows_project("p1") is False


def test_resolve_from_env(monkeypatch):
    monkeypatch.setenv(
        capabilities.ENV_VAR,
        '{"tier":"propose","workspace_id":"w","project_ids":["p"],"label":"x"}',
    )
    cap = capabilities.resolve_capability()
    assert cap.valid and cap.tier == "propose"


def test_resolve_missing_env_denies(monkeypatch):
    monkeypatch.delenv(capabilities.ENV_VAR, raising=False)
    assert capabilities.resolve_capability().valid is False
