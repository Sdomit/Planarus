"""Phase 7C0: framework-neutral domain-exception boundary.

Verifies that domain exceptions live in a FastAPI-free module, that the
service/policy/MCP layers don't import the HTTP-boundary module, that importing
those layers doesn't transitively load FastAPI, and that the existing HTTP
exception mappings are byte-for-byte unchanged.
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import pathlib
import subprocess
import sys

import app.core.errors as errors_mod
import app.core.exceptions as exceptions_mod

APP_DIR = pathlib.Path(exceptions_mod.__file__).resolve().parents[1]  # apps/api/app
API_DIR = APP_DIR.parent  # apps/api

_FORBIDDEN_IMPORT_ROOTS = (
    "fastapi",
    "starlette",
    "pydantic",
    "sqlmodel",
    "sqlalchemy",
    "mcp",
)


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                roots.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_exceptions_module_is_framework_neutral():
    roots = _imported_roots(APP_DIR / "core" / "exceptions.py")
    leaked = roots & set(_FORBIDDEN_IMPORT_ROOTS)
    assert not leaked, f"exceptions.py imports framework module(s): {leaked}"


def test_domain_layers_do_not_import_core_errors():
    offenders = []
    for layer in ("services", "policy", "mcp"):
        for path in (APP_DIR / layer).rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            if "app.core.errors" in src:
                offenders.append(str(path.relative_to(API_DIR)))
    assert offenders == [], f"domain layers still import app.core.errors: {offenders}"


def test_mcp_and_services_import_without_fastapi_or_core_errors():
    """In a clean process, importing the MCP/service/policy layers must not pull in
    FastAPI or the HTTP-boundary module (app.core.errors)."""
    script = (
        "import sys\n"
        "import app.mcp.registry, app.mcp.capabilities, app.mcp.serializers\n"
        "import app.mcp.tools.read, app.mcp.tools.propose\n"
        "import app.services.approval_service, app.services.project_service\n"
        "import app.policy.allowlist, app.policy.binding, app.policy.handlers\n"
        "assert 'app.core.errors' not in sys.modules, 'app.core.errors leaked'\n"
        "assert 'fastapi' not in sys.modules, 'fastapi leaked'\n"
        "print('OK')\n"
    )
    env = {**os.environ, "PYTHONPATH": str(API_DIR)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_http_exception_mappings_unchanged():
    """The FastAPI handlers still map each domain exception to its status + shape."""
    cases = [
        (errors_mod.conflict_handler, exceptions_mod.ConflictError("dup"), 409, "dup"),
        (errors_mod.unprocessable_handler, exceptions_mod.PolicyError("bad field"), 422, "bad field"),
        (errors_mod.unprocessable_handler, exceptions_mod.SecretDetectedError(), 422, None),
        (errors_mod.approval_conflict_handler, exceptions_mod.ApprovalConflictError("stale"), 409, "stale"),
        (errors_mod.server_error_handler, exceptions_mod.ApprovalApplyError("boom"), 500, "boom"),
    ]
    for handler, exc, status, detail in cases:
        resp = asyncio.run(handler(None, exc))
        assert resp.status_code == status
        body = json.loads(resp.body)
        assert set(body) == {"detail"}
        if detail is not None:
            assert body["detail"] == detail
        else:
            assert isinstance(body["detail"], str) and body["detail"]


def test_backward_compatible_reexports():
    """The HTTP boundary still re-exports the classes (same objects)."""
    for name in (
        "ConflictError",
        "ApprovalConflictError",
        "PolicyError",
        "SecretDetectedError",
        "ApprovalApplyError",
    ):
        assert getattr(errors_mod, name) is getattr(exceptions_mod, name)
