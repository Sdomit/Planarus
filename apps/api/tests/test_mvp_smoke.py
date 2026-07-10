"""MVP release gate (Phase 8): one end-to-end smoke flow proving the seven
essential MVP surfaces work against a live API. Each surface maps to the
endpoint(s) its UI depends on; the flow seeds real data then exercises them.

Surfaces: Dashboard, Cockpit, Tree, Task Board, basic Docs, AI Context/Prompt,
Approval Queue.
"""
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "MVP WS", "slug": "mvp-ws"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "MVP Project", "slug": "mvp-project"},
    ).json()
    pid = proj["id"]
    client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Build", "status": "active"})
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Do a thing", "status": "in_progress"})
    client.post(f"/api/v1/projects/{pid}/docs", json={"title": "Spec", "doc_type": "spec"})
    return ws["id"], pid


def test_mvp_seven_surfaces_smoke(client: TestClient) -> None:
    ws_id, pid = _seed(client)
    results: dict[str, bool] = {}

    def ok(resp) -> bool:
        return resp.status_code == 200

    # 1. Dashboard — workspaces, projects, pending approvals aggregate. Assert
    # the seeded rows actually come back (a silently-ignored filter would 200 []).
    ws_resp = client.get("/api/v1/workspaces")
    proj_resp = client.get(f"/api/v1/projects?workspace_id={ws_id}")
    results["Dashboard"] = (
        ok(ws_resp) and len(ws_resp.json()) >= 1
        and ok(proj_resp) and any(p["id"] == pid for p in proj_resp.json())
        and ok(client.get("/api/v1/approvals?status=pending"))
    )

    # 2. Cockpit — project detail + read-only Git summary.
    proj = client.get(f"/api/v1/projects/{pid}")
    git = client.get(f"/api/v1/projects/{pid}/git")
    results["Cockpit"] = ok(proj) and ok(git) and "is_repo" in git.json()

    # 3. Tree — phase/stage hierarchy.
    phases = client.get(f"/api/v1/projects/{pid}/phases")
    results["Tree"] = (
        ok(phases)
        and ok(client.get(f"/api/v1/projects/{pid}/stages"))
        and len(phases.json()) == 1
    )

    # 4. Task Board — tasks list.
    tasks = client.get(f"/api/v1/projects/{pid}/tasks")
    results["Task Board"] = ok(tasks) and len(tasks.json()) == 1

    # 5. basic Docs — list + fetch one doc's content.
    docs = client.get(f"/api/v1/projects/{pid}/docs")
    doc_ok = ok(docs) and len(docs.json()) == 1
    if doc_ok:
        doc_ok = ok(client.get(f"/api/v1/docs/{docs.json()[0]['id']}"))
    results["basic Docs"] = doc_ok

    # 6. AI Context/Prompt — profiles, resolvable sources, and a real preview.
    profiles = client.get("/api/v1/context-pack/profiles")
    sources = client.get(f"/api/v1/projects/{pid}/context-pack/sources")
    profiles_ok = ok(profiles) and len(profiles.json().get("profiles", [])) >= 1
    sources_ok = ok(sources) and "structured" in sources.json()
    preview_ok = False
    if profiles_ok:
        prof = profiles.json()
        preview = client.post(
            f"/api/v1/projects/{pid}/context-pack/preview",
            json={
                "profile": prof["profiles"][0]["key"],
                "target_tool": prof["target_tools"][0],
                "budget_preset": prof["default_budget_preset"],
                "objective": "smoke check",
                "selection": {},
            },
        )
        preview_ok = ok(preview) and bool(preview.json().get("markdown"))
    results["AI Context/Prompt"] = profiles_ok and sources_ok and preview_ok

    # 7. Approval Queue — queue list + local control session.
    results["Approval Queue"] = (
        ok(client.get("/api/v1/approvals"))
        and ok(client.get("/api/v1/local-session"))
    )

    failed = [name for name, passed in results.items() if not passed]
    assert not failed, f"MVP surfaces failed smoke: {failed}"
    assert len(results) == 7
