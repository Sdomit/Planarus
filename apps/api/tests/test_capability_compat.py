"""Phase 7C1: Capability compatibility for MCP + external API.

The Phase 7B MCP behaviour must be byte-identical; the new can_read/can_propose
booleans let API keys grant the two independently.
"""
from app.mcp import registry
from app.mcp.capabilities import (
    DENY,
    Capability,
    capability_from_api_client,
    parse_capability,
)
from app.mcp.registry import PROPOSE_TOOL_NAMES, READ_TOOL_NAMES

from tests.mcp_util import EXPECTED_PROPOSE_TOOLS, EXPECTED_READ_TOOLS


def _env(tier):
    import json

    return json.dumps({"tier": tier, "workspace_id": "w", "project_ids": ["p1"]})


def test_mcp_tier_read_maps_to_read_only():
    cap = parse_capability(_env("read"))
    assert cap.valid and cap.tier == "read"
    assert cap.can_read is True and cap.can_propose is False
    assert cap.actor_ref == "mcp:client"  # default label
    names = registry.visible_names(cap)
    assert names == set(READ_TOOL_NAMES)


def test_mcp_tier_propose_maps_to_read_plus_propose():
    cap = parse_capability(_env("propose"))
    assert cap.valid and cap.tier == "propose"
    assert cap.can_read is True and cap.can_propose is True
    names = registry.visible_names(cap)
    assert names == set(READ_TOOL_NAMES) | set(PROPOSE_TOOL_NAMES)


def test_legacy_capability_construction_still_derives_booleans():
    # Existing MCP test/util construction passes tier only.
    r = Capability(tier="read", workspace_id="w", project_ids=frozenset({"p"}), label="l")
    p = Capability(tier="propose", workspace_id="w", project_ids=frozenset({"p"}), label="l")
    assert (r.can_read, r.can_propose) == (True, False)
    assert (p.can_read, p.can_propose) == (True, True)
    assert r.actor_ref == "mcp:l" and p.actor_ref == "mcp:l"


def test_registry_sets_are_unchanged():
    assert READ_TOOL_NAMES == EXPECTED_READ_TOOLS
    assert PROPOSE_TOOL_NAMES == EXPECTED_PROPOSE_TOOLS
    # No approve/apply-style tool exists anywhere.
    forbidden = ("approve", "apply", "reject", "invalidate", "delete")
    for name in set(READ_TOOL_NAMES) | set(PROPOSE_TOOL_NAMES):
        assert not any(f in name for f in forbidden)


def test_deny_has_no_powers():
    assert DENY.valid is False
    assert DENY.can_read is False and DENY.can_propose is False
    assert registry.visible_names(DENY) == set()


def test_api_capability_read_only_cannot_propose():
    cap = capability_from_api_client(
        workspace_id="w", key_id="kid", project_ids=frozenset({"p"}),
        label="k", can_read=True, can_propose=False,
    )
    assert cap.origin == "api" and cap.actor_ref == "api:kid"
    assert cap.can_read is True and cap.can_propose is False


def test_api_capability_propose_only_cannot_read():
    cap = capability_from_api_client(
        workspace_id="w", key_id="kid", project_ids=frozenset({"p"}),
        label="k", can_read=False, can_propose=True,
    )
    assert cap.can_read is False and cap.can_propose is True
    assert cap.origin == "api" and cap.actor_ref == "api:kid"


def test_capability_has_no_approve_or_apply_attribute():
    cap = capability_from_api_client(
        workspace_id="w", key_id="k", project_ids=frozenset({"p"}),
        label="k", can_read=True, can_propose=True,
    )
    for attr in ("can_approve", "can_apply", "approve", "apply"):
        assert not hasattr(cap, attr)
