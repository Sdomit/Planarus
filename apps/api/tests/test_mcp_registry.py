import ast
import pathlib

import app.mcp
from app.mcp import capabilities, registry
from app.mcp.capabilities import Capability

_READ = {
    "list_projects",
    "get_project_summary",
    "get_active_work",
    "list_tasks",
    "list_decisions",
    "list_risks",
    "list_docs",
    "get_doc_excerpt",
    "get_approval_status",
}
_PROPOSE = {"create_task_proposal", "update_task_proposal", "create_decision_proposal"}


def test_exact_read_names():
    assert set(registry.READ_TOOL_NAMES) == _READ


def test_exact_propose_names():
    assert set(registry.PROPOSE_TOOL_NAMES) == _PROPOSE


def test_read_tier_sees_only_read_tools():
    cap = Capability(tier="read", workspace_id="w", project_ids=frozenset({"p"}), label="l")
    names = registry.visible_names(cap)
    assert names == _READ
    assert names.isdisjoint(_PROPOSE)


def test_propose_tier_sees_twelve():
    cap = Capability(tier="propose", workspace_id="w", project_ids=frozenset({"p"}), label="l")
    names = registry.visible_names(cap)
    assert names == _READ | _PROPOSE
    assert len(names) == 12


def test_default_deny_sees_nothing():
    assert registry.visible_specs(capabilities.DENY) == []
    assert registry.visible_names(capabilities.DENY) == set()


def test_no_forbidden_substrings_in_names():
    for name in set(registry.READ_TOOL_NAMES) | set(registry.PROPOSE_TOOL_NAMES):
        low = name.lower()
        bad = [s for s in registry.FORBIDDEN_NAME_SUBSTRINGS if s in low]
        assert not bad, f"{name} contains forbidden substring {bad}"


def test_no_mutation_or_apply_tool_present():
    all_names = set(registry.READ_TOOL_NAMES) | set(registry.PROPOSE_TOOL_NAMES)
    for forbidden in ("approve", "apply", "reject", "invalidate", "delete", "archive"):
        assert not any(forbidden in n for n in all_names)


def test_mcp_source_does_not_import_mutators():
    """No MCP module may import or call apply/approve/reject/invalidate or
    policy.handlers. AST-based so docstrings that *mention* them don't false-fire."""
    mcp_dir = pathlib.Path(app.mcp.__file__).parent
    mutating_attrs = {"approve", "apply", "reject", "invalidate"}
    mutating_owners = {"approval_service", "handlers"}
    offenders = []
    for path in mcp_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.endswith("handlers"):
                    offenders.append(f"{path.name}: from {mod}")
                if mod == "app.policy" and any(a.name == "handlers" for a in node.names):
                    offenders.append(f"{path.name}: from app.policy import handlers")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.endswith(".handlers") or a.name == "handlers":
                        offenders.append(f"{path.name}: import {a.name}")
            elif isinstance(node, ast.Attribute) and node.attr in mutating_attrs:
                val = node.value
                if isinstance(val, ast.Name) and val.id in mutating_owners:
                    offenders.append(f"{path.name}: {val.id}.{node.attr}")
    assert offenders == [], offenders


def test_mcp_only_server_imports_sdk():
    """Only server.py may import the `mcp` SDK; tool logic stays SDK-agnostic."""
    mcp_dir = pathlib.Path(app.mcp.__file__).parent
    for path in mcp_dir.rglob("*.py"):
        if path.name == "server.py":
            continue
        src = path.read_text(encoding="utf-8")
        assert "import mcp" not in src and "from mcp" not in src, f"{path.name} imports the SDK"
