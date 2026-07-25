"""Single-instance runtime contract (#120).

Pre-1.0 Planarus supports exactly **one API process and one replica**. That is
not a packaging accident — several security and coordination controls are
process-local by design:

- login rate-limit buckets and external-API concurrency counters
  (``core/rate_limit.py``: the module-level ``limiter`` holds ``_read``,
  ``_propose``, ``_concurrency`` and ``_auth`` behind a ``threading.Lock``) are
  in-memory, so N workers give an attacker N times the budget;
- the local control token (``core/security.py:_LOCAL_CONTROL_TOKEN``) is minted
  once per process, so a token issued by one worker is rejected by the other;
- the LAN acceptance switch (``services/settings_service.py:_lan_switch_cache``)
  is a process-memory mirror of the DB switch, so turning LAN mode *off* only
  reaches the worker that served the write;
- document presence and soft-locks are in-process by design;
- local filesystem storage and managed project roots assume one local API node;
- ``storage/s3.py:append_line`` is read-modify-write, which loses concurrent
  writes without a distributed lock.

OAuth is **no longer** in this list: #113 replaced the per-process HMAC state key
with a server-side one-time ``oauthtransaction`` row shared by the login and
calendar flows, so OAuth state already survives both a restart and a second
worker. Issue #120's original evidence predates that fix.

Only the **worker count** is detectable from inside the process, and only when
it was configured through the environment. Replica count, rolling-deploy
overlap and autoscaling are platform-side and cannot be observed here — they are
stated as operator obligations in ``docs/guide/hosted-go-live.md``.

ponytail: env-var detection only. A hand-written ``--workers 4`` on the command
line is invisible to the forked child; the pinned start command plus the
documented contract cover that. Add process-tree detection only if someone
actually gets bitten.
"""
from __future__ import annotations

import os
from typing import Optional

#: Env vars that make a server fork more than one worker. ``WEB_CONCURRENCY`` is
#: read by uvicorn (``uvicorn/config.py``) and by gunicorn; ``UVICORN_WORKERS``
#: is uvicorn's click ``auto_envvar_prefix="UVICORN"`` mapping for ``--workers``.
WORKER_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS")

_CONTRACT_HINT = (
    "Planarus pre-1.0 supports exactly one API process and one replica (#120): "
    "rate-limit buckets, the local control token, the LAN switch mirror and "
    "presence are process-local, so a second worker multiplies the rate limits "
    "and splits the control token. See docs/guide/hosted-go-live.md."
)


def worker_count_violation() -> Optional[str]:
    """Return a human-readable reason if the env configures >1 worker, else None.

    An unparseable value is treated as a violation: a platform that sets
    ``WEB_CONCURRENCY=auto`` is a platform that intends to scale.
    """
    for name in WORKER_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            count = int(raw)
        except ValueError:
            return f"{name}={raw!r} is not a plain integer — cannot prove a single-worker deploy. {_CONTRACT_HINT}"
        if count > 1:
            return f"{name}={count} would fork {count} worker processes. {_CONTRACT_HINT}"
    return None


def shared_state_warnings(storage_backend: str) -> list[str]:
    """Non-enforceable single-instance assumptions worth printing at preflight.

    These cannot be checked from inside one process; the operator has to
    guarantee them at the platform. Returned as plain strings so the caller
    decides how to render them.
    """
    warnings = [
        "replica/instance count must be exactly 1 — no autoscaling, no rolling "
        "deploy that runs old and new instances concurrently (not detectable here)",
        "a restart re-mints the local control token and clears rate-limit "
        "buckets and presence; OAuth sign-ins survive it (#113 made the "
        "transaction a DB row)",
    ]
    if storage_backend == "s3":
        warnings.append(
            "S3 append is read-modify-write and has no distributed lock — "
            "concurrent appends from two instances lose data; single-instance "
            "hosting is what makes it safe"
        )
    return warnings
