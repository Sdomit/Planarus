"""P17.5 — the GPT Actions OpenAPI serving endpoint (Integrations hub).

Asserts the endpoint returns exactly the pure builder output, so it stays a
mirror of the committed docs/api/*.openapi.json (drift is caught in
test_openapi_contract.py, which owns files-vs-builders).
"""


def test_gpt_openapi_serves_readonly_contract_by_default(client):
    from app.api.external.openapi import build_readonly_openapi

    r = client.get("/api/v1/integrations/gpt-openapi")
    assert r.status_code == 200
    assert r.json() == build_readonly_openapi()


def test_gpt_openapi_serves_read_propose_profile_on_request(client):
    from app.api.external.openapi import build_read_propose_openapi

    r = client.get("/api/v1/integrations/gpt-openapi", params={"profile": "read_propose"})
    assert r.status_code == 200
    assert r.json() == build_read_propose_openapi()
