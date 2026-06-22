"""Phase 7C2a — contract drift + safety tests for the static GPT Actions OpenAPI docs.

These assert the committed artifacts equal the pure builder output, that the contract
mirrors the LIVE Phase 7C1 external router exactly (no more, no fewer operations),
that no forbidden surface leaks in, that the GPT-Actions consequential flags are
explicit, and that real TestClient responses match the declared response shapes — all
WITHOUT enabling the external API outside the existing controlled `external_api`
fixture. No real ApiClient key is created outside the test fixtures, and no OpenAPI
artifact is served or route mounted.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from app.api.external.openapi import (
    CONTRACT_VERSION,
    MAX_DOC_EXCERPT_CHARS as C_MAX_DOC_EXCERPT_CHARS,
    MAX_LIST_ROWS as C_MAX_LIST_ROWS,
    PROPOSE_PROFILE_NOTE,
    READONLY_PROFILE_NOTE,
    REVIEW_HINT as C_REVIEW_HINT,
    SERVER_URL,
    build_read_propose_openapi,
    build_readonly_openapi,
)
from app.api.external.router import _TaskUpdateBody
from app.api.external.router import router as external_router
from app.api.v1.router import router as internal_router
from app.core.constants import DOC_TYPES
from app.core.utils import new_id, now_utc
from app.main import app
from app.mcp.serializers import MAX_DOC_EXCERPT_CHARS, MAX_LIST_ROWS
from app.mcp.tools.propose import (
    REVIEW_HINT,
    CreateDecisionProposalArgs,
    CreateTaskProposalArgs,
)
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.task import Task
from app.services import approval_service
from tests.external_util import auth, issue_key, seed

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_API = REPO_ROOT / "docs" / "api"
READONLY_FILE = DOCS_API / "agentboard-gpt-actions-readonly.openapi.json"
PROPOSE_FILE = DOCS_API / "agentboard-gpt-actions-read-propose.openapi.json"

READ_OPERATION_IDS = {
    "listProjects", "getProjectSummary", "listTasks", "listDecisions",
    "listRisks", "listDocs", "getDocExcerpt", "getApprovalStatus",
}
PROPOSE_OPERATION_IDS = {"proposeTaskCreate", "proposeTaskUpdate", "proposeDecisionCreate"}

# Checked against PATHS and OPERATION IDS only — never against descriptions, which
# legitimately mention "API key", etc.
FORBIDDEN_SUBSTRINGS = (
    "approve", "apply", "reject", "invalidate", "delete", "archive", "import",
    "export", "context-pack", "context_pack", "api-client", "api_client", "key",
    "local-control", "local_control", "filesystem", "shell", "git", "command",
    "network",
)

EXTERNAL_BASE = "/api/external/v1"
INTERNAL_BASE = "/api/v1"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


# --- helpers -----------------------------------------------------------------


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract_pairs(doc: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in doc["paths"].items()
        for method in item
    }


def _operations(doc: dict):
    for path, item in doc["paths"].items():
        for method, op in item.items():
            yield path, method, op


def _live_external_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in external_router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in {"GET", "POST"}:
                pairs.add((method, path))
    return pairs


# --- 1/2/3: parse, version, artifact == builder ------------------------------


def test_artifacts_parse_as_valid_json():
    assert isinstance(_load(READONLY_FILE), dict)
    assert isinstance(_load(PROPOSE_FILE), dict)


def test_openapi_version_is_3_1_0():
    assert build_readonly_openapi()["openapi"] == "3.1.0"
    assert build_read_propose_openapi()["openapi"] == "3.1.0"
    assert _load(READONLY_FILE)["openapi"] == "3.1.0"
    assert _load(PROPOSE_FILE)["openapi"] == "3.1.0"


def test_artifacts_equal_builder_output_exactly():
    assert _load(READONLY_FILE) == build_readonly_openapi()
    assert _load(PROPOSE_FILE) == build_read_propose_openapi()


def test_builder_is_deterministic_and_independent():
    a, b = build_read_propose_openapi(), build_read_propose_openapi()
    assert a == b and a is not b
    a["paths"].clear()  # mutating one result must not affect a fresh build
    assert build_read_propose_openapi()["paths"]


# --- 4/5: operation counts ----------------------------------------------------


def test_readonly_profile_has_exactly_8_operations():
    ro = build_readonly_openapi()
    assert sum(len(item) for item in ro["paths"].values()) == 8
    assert {op["operationId"] for _, _, op in _operations(ro)} == READ_OPERATION_IDS


def test_read_propose_profile_has_exactly_11_operations():
    rp = build_read_propose_openapi()
    assert sum(len(item) for item in rp["paths"].values()) == 11
    assert {op["operationId"] for _, _, op in _operations(rp)} == (
        READ_OPERATION_IDS | PROPOSE_OPERATION_IDS
    )


# --- 6/7: parity with the live Phase 7C1 external router ----------------------


def test_full_profile_matches_live_external_router_exactly():
    assert _contract_pairs(build_read_propose_openapi()) == _live_external_pairs()


def test_readonly_profile_is_exactly_the_get_subset():
    live_gets = {(m, p) for (m, p) in _live_external_pairs() if m == "GET"}
    contract = _contract_pairs(build_readonly_openapi())
    assert contract == live_gets
    assert all(m == "GET" for (m, _) in contract)


# --- 8: no intersection with internal /api/v1 --------------------------------


def test_no_contract_path_intersects_internal_v1():
    base = urlsplit(SERVER_URL).path  # "/api/external/v1"
    assert base == EXTERNAL_BASE
    rp = build_read_propose_openapi()
    external_full = {(m, base + p) for (m, p) in _contract_pairs(rp)}
    internal_full: set[tuple[str, str]] = set()
    for route in internal_router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in HTTP_METHODS:
                internal_full.add((method, INTERNAL_BASE + path))
    assert external_full.isdisjoint(internal_full)
    assert all(INTERNAL_BASE not in p for p in rp["paths"])


# --- 9: no forbidden operation or path ---------------------------------------


def test_no_forbidden_operation_or_path():
    for doc in (build_readonly_openapi(), build_read_propose_openapi()):
        for path, _, op in _operations(doc):
            low_path = path.lower()
            assert not any(s in low_path for s in FORBIDDEN_SUBSTRINGS), path
            low_id = op["operationId"].lower()
            assert not any(s in low_id for s in FORBIDDEN_SUBSTRINGS), op["operationId"]


# --- 10/11: explicit consequential flags -------------------------------------


def test_consequential_flags_are_explicit_per_method():
    for doc in (build_readonly_openapi(), build_read_propose_openapi()):
        for _, method, op in _operations(doc):
            assert "x-openai-isConsequential" in op
            if method == "get":
                assert op["x-openai-isConsequential"] is False
            elif method == "post":
                assert op["x-openai-isConsequential"] is True
            else:  # pragma: no cover - contract only uses get/post
                raise AssertionError(f"unexpected method {method}")


# --- 12: bearer security scheme ----------------------------------------------


def test_bearer_http_security_scheme_declared():
    for doc in (build_readonly_openapi(), build_read_propose_openapi()):
        scheme = doc["components"]["securitySchemes"]["bearerAuth"]
        assert scheme["type"] == "http"
        assert scheme["scheme"] == "bearer"
        assert {"bearerAuth": []} in doc["security"]


# --- 13: safe RFC 9457 problem responses on every operation ------------------


def test_every_operation_declares_safe_problem_responses():
    for doc in (build_readonly_openapi(), build_read_propose_openapi()):
        responses_components = doc["components"]["responses"]
        for _, _, op in _operations(doc):
            statuses = set(op["responses"])
            assert any(s.startswith("2") for s in statuses)
            assert {"401", "429", "503"} <= statuses
            for status, resp in op["responses"].items():
                if int(status) >= 400:
                    assert set(resp) == {"$ref"}, status
                    name = resp["$ref"].split("/")[-1]
                    component = responses_components[name]
                    schema_ref = component["content"]["application/problem+json"]["schema"]["$ref"]
                    assert schema_ref.endswith("/Problem")
        # The Problem schema has no invented `code` property.
        problem_props = set(doc["components"]["schemas"]["Problem"]["properties"])
        assert problem_props == {"type", "title", "status", "detail", "instance"}
        assert "code" not in problem_props


# --- 14/15: proposal result + no unsafe proposal fields ----------------------


def test_proposal_result_has_exactly_five_fields_and_pinned_hint():
    rp = build_read_propose_openapi()
    pr = rp["components"]["schemas"]["ProposalResult"]
    five = {"approval_id", "status", "action_type", "expires_at", "review_hint"}
    assert set(pr["properties"]) == five
    assert set(pr["required"]) == five
    assert pr["additionalProperties"] is False
    assert pr["properties"]["review_hint"]["description"] == REVIEW_HINT
    assert pr["properties"]["review_hint"]["examples"] == [REVIEW_HINT]
    assert REVIEW_HINT in pr["description"]


def test_no_proposal_schema_exposes_unsafe_fields():
    rp = build_read_propose_openapi()
    banned = (
        "patch", "diff", "secret", "password", "token", "credential", "apikey",
        "api_key", "approve", "apply", "workspace_id", "checksum", "audit",
    )
    for name in (
        "TaskProposalCreate", "TaskProposalUpdate", "DecisionProposalCreate",
        "ProposalResult",
    ):
        schema = rp["components"]["schemas"][name]
        for prop in schema["properties"]:
            low = prop.lower()
            assert not any(b in low for b in banned), (name, prop)


# --- 16: GPT Actions length limits -------------------------------------------


def test_summary_and_description_length_limits():
    for doc in (build_readonly_openapi(), build_read_propose_openapi()):
        for _, _, op in _operations(doc):
            assert len(op["summary"]) <= 300
            assert len(op["description"]) <= 300
            for param in op.get("parameters", []):
                assert len(param.get("description", "")) <= 700


# --- 17: request fields + bounds match the live models -----------------------


def _props(doc: dict, name: str) -> set[str]:
    return set(doc["components"]["schemas"][name]["properties"])


def _required(doc: dict, name: str) -> set[str]:
    return set(doc["components"]["schemas"][name].get("required", []))


def _live_required(model) -> set[str]:
    return {n for n, f in model.model_fields.items() if f.is_required()}


def test_request_schemas_match_live_models_and_bounds():
    rp = build_read_propose_openapi()

    assert _props(rp, "TaskProposalCreate") == set(CreateTaskProposalArgs.model_fields)
    assert _required(rp, "TaskProposalCreate") == _live_required(CreateTaskProposalArgs)

    assert _props(rp, "TaskProposalUpdate") == set(_TaskUpdateBody.model_fields)
    assert "project_id" not in _props(rp, "TaskProposalUpdate")
    assert _required(rp, "TaskProposalUpdate") == set()  # all optional

    assert _props(rp, "DecisionProposalCreate") == set(CreateDecisionProposalArgs.model_fields)
    assert _required(rp, "DecisionProposalCreate") == _live_required(CreateDecisionProposalArgs)

    # extra="forbid" → additionalProperties False on every request body.
    for name in ("TaskProposalCreate", "TaskProposalUpdate", "DecisionProposalCreate"):
        assert rp["components"]["schemas"][name]["additionalProperties"] is False

    # Query bounds mirror the live serializer constants, and the builder literals
    # match the live values (drift guard).
    limit_schema = max_chars_schema = None
    for _, _, op in _operations(rp):
        for param in op.get("parameters", []):
            if param["name"] == "limit":
                limit_schema = param["schema"]
            elif param["name"] == "max_chars":
                max_chars_schema = param["schema"]
    assert limit_schema["maximum"] == limit_schema["default"] == MAX_LIST_ROWS
    assert max_chars_schema["maximum"] == max_chars_schema["default"] == MAX_DOC_EXCERPT_CHARS
    assert C_MAX_LIST_ROWS == MAX_LIST_ROWS
    assert C_MAX_DOC_EXCERPT_CHARS == MAX_DOC_EXCERPT_CHARS
    assert C_REVIEW_HINT == REVIEW_HINT


def test_profiles_are_visibly_marked():
    ro, rp = build_readonly_openapi(), build_read_propose_openapi()
    assert ro["info"]["x-agentboard-profile-note"] == READONLY_PROFILE_NOTE
    assert READONLY_PROFILE_NOTE in ro["info"]["description"]
    assert rp["info"]["x-agentboard-profile-note"] == PROPOSE_PROFILE_NOTE
    assert PROPOSE_PROFILE_NOTE in rp["info"]["description"]
    assert "Do not import this profile" in PROPOSE_PROFILE_NOTE
    assert ro["info"]["version"] == rp["info"]["version"] == CONTRACT_VERSION


# --- 18: real responses match the declared response shapes -------------------


@pytest.fixture
def world(client, external_api, session):
    ws, proj = seed(client, "c2a")
    now = now_utc()
    task = Task(
        id=new_id("tsk"), project_id=proj, title="t", status="in_progress",
        sort_order=0, created_at=now, updated_at=now,
    )
    doc = Doc(
        id=new_id("doc"), project_id=proj, title="Doc", slug="doc-c2a",
        doc_type=DOC_TYPES[0], markdown_cache="# heading\nbody", created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.add(
        Decision(
            id=new_id("dec"), project_id=proj, title="d", decision="x",
            context="c", status="accepted", created_at=now, updated_at=now,
        )
    )
    session.add(doc)
    session.commit()
    ar = approval_service.create_proposal(
        session, project_id=proj, action_type="task.create",
        patch={"title": "pending"},
    )
    return SimpleNamespace(ws=ws, proj=proj, task_id=task.id, doc_id=doc.id, approval_id=ar.id)


def test_read_responses_match_contract_read_result_shape(world, client):
    expected = set(build_readonly_openapi()["components"]["schemas"]["ReadResult"]["properties"])
    assert expected == {"metadata", "text"}
    _, raw = issue_key(client, world.ws, [world.proj], can_read=True, can_propose=False)
    headers = auth(raw)
    urls = {
        "listProjects": f"{EXTERNAL_BASE}/projects",
        "getProjectSummary": f"{EXTERNAL_BASE}/projects/{world.proj}/summary",
        "listTasks": f"{EXTERNAL_BASE}/projects/{world.proj}/tasks",
        "listDecisions": f"{EXTERNAL_BASE}/projects/{world.proj}/decisions",
        "listRisks": f"{EXTERNAL_BASE}/projects/{world.proj}/risks",
        "listDocs": f"{EXTERNAL_BASE}/projects/{world.proj}/docs",
        "getDocExcerpt": f"{EXTERNAL_BASE}/docs/{world.doc_id}/excerpt",
        "getApprovalStatus": f"{EXTERNAL_BASE}/approvals/{world.approval_id}/status",
    }
    for op_id, url in urls.items():
        res = client.get(url, headers=headers)
        assert res.status_code == 200, (op_id, res.status_code, res.text)
        assert set(res.json()) == expected, op_id


def test_proposal_responses_match_contract_proposal_result_shape(world, client):
    expected = set(build_read_propose_openapi()["components"]["schemas"]["ProposalResult"]["properties"])
    _, raw = issue_key(client, world.ws, [world.proj], can_read=False, can_propose=True)
    headers = auth(raw)

    r1 = client.post(
        f"{EXTERNAL_BASE}/proposals/task", headers=headers,
        json={"project_id": world.proj, "title": "Do it"},
    )
    assert r1.status_code == 202, r1.text
    assert set(r1.json()) == expected

    r2 = client.post(
        f"{EXTERNAL_BASE}/proposals/task/{world.task_id}", headers=headers,
        json={"status": "in_progress"},
    )
    assert r2.status_code == 202, r2.text
    assert set(r2.json()) == expected

    r3 = client.post(
        f"{EXTERNAL_BASE}/proposals/decision", headers=headers,
        json={"project_id": world.proj, "title": "Pick X", "decision": "use X"},
    )
    assert r3.status_code == 202, r3.text
    assert set(r3.json()) == expected


# --- 19/20: no runtime route added; API disabled by default ------------------


def test_no_runtime_external_route_added_or_served():
    # `external_router` is the exact object main.py mounts at /api/external/v1, so its
    # APIRoute set IS the mounted external surface (this FastAPI version keeps included
    # routers as lazy `_IncludedRouter` wrappers, so app.routes is not flattened).
    from fastapi import APIRouter, FastAPI
    from fastapi.routing import APIRoute

    routes = [r for r in external_router.routes if isinstance(r, APIRoute)]
    pairs = {
        (m, r.path) for r in routes for m in (r.methods or set()) if m in {"GET", "POST"}
    }
    # Exactly the 11 live external operations — nothing new mounted.
    assert len(routes) == 11
    assert pairs == _live_external_pairs()
    # No served OpenAPI artifact / contract route was mounted on the external surface.
    for r in routes:
        assert "openapi" not in r.path.lower()
        assert "contract" not in r.path.lower()
    # The builder module is a pure dict builder — it exposes no mountable FastAPI
    # router or app, so importing it cannot register a route.
    import app.api.external.openapi as builder_module

    assert not hasattr(builder_module, "router")
    assert not any(
        isinstance(v, (APIRouter, FastAPI)) for v in vars(builder_module).values()
    )


def test_external_api_remains_disabled_by_default():
    # No `external_api` fixture → AGENTBOARD_EXTERNAL_API_ENABLED defaults to False.
    from fastapi.testclient import TestClient

    res = TestClient(app).get(
        f"{EXTERNAL_BASE}/projects",
        headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_a_b"},
    )
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
