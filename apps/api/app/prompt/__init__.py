"""Local-only prompt + context-pack generation (Phase 6A).

Pure, deterministic, side-effect-free building blocks for the Context Pack
Builder. Nothing in this package calls an external AI API, opens a network
socket, writes files, mutates the database, or emits audit events. The service
layer (`app.services.context_pack_service`) orchestrates these modules; the API
layer exposes preview + copy only.

Modules:
- `profiles`  — static, versioned built-in prompt profiles (no DB templates).
- `tokens`    — approximate token budgeting + deterministic trim order.
- `boundary`  — injection-boundary wrapping, marker/role defanging, suspicious-
                text detection. All project content is untrusted reference data.
- `secrets`   — best-effort secret-pattern detection; never returns raw values.
"""
