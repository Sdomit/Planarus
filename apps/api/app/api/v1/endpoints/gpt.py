"""P17.5 — serves the curated GPT Actions OpenAPI contract to the Integrations
hub's ChatGPT card (for copy-paste into a private "Only me" GPT).

A pure mirror of the deterministic builders in ``app/api/external/openapi.py``
(the same source as the committed ``docs/api/*.openapi.json``), so it can never
drift. Reachable at the web origin via ``/api/*``; note the ChatGPT setup tunnel
deliberately forwards only ``/api/external/*``, so this is a local-UI convenience,
not a public import URL. Read-only by default; the read+propose profile is gated
and marked "do not import for a first live GPT" in the contract itself.
"""
from fastapi import APIRouter, Query

from app.api.external.openapi import build_read_propose_openapi, build_readonly_openapi

router = APIRouter()


@router.get("/integrations/gpt-openapi")
def get_gpt_openapi(profile: str = Query("readonly")) -> dict:
    if profile == "read_propose":
        return build_read_propose_openapi()
    return build_readonly_openapi()
