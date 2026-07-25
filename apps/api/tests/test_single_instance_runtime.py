"""#120 — the single-instance runtime contract.

Pre-1.0 Planarus supports exactly one API process and one replica because the
rate-limit buckets, the local control token, the LAN switch mirror and document
presence are all process-local. These tests pin the two enforceable halves (the
startup refusal and the doctor check) and the process-local behaviours that make
the contract necessary, so a future change that quietly makes them shared has to
update this file deliberately.

OAuth state is deliberately asserted to be the *opposite* — #113 moved it to a
DB row, so #120's original evidence list is stale on that one point.
"""
import importlib.util
import pathlib

import pytest
from app.core.config import settings
from app.core.runtime import (
    WORKER_ENV_VARS,
    shared_state_warnings,
    worker_count_violation,
)

_DOCTOR_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("planarus_doctor_runtime", _DOCTOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod  # fresh module → _fails/_warns start at 0


@pytest.fixture(autouse=True)
def _clean_worker_env(monkeypatch):
    """The dev box may export these; every test starts from a known-clean env."""
    for name in WORKER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# --- detection ---------------------------------------------------------------


def test_unset_worker_env_is_compliant():
    assert worker_count_violation() is None


@pytest.mark.parametrize("name", WORKER_ENV_VARS)
def test_single_worker_is_compliant(monkeypatch, name):
    monkeypatch.setenv(name, "1")
    assert worker_count_violation() is None


@pytest.mark.parametrize("name", WORKER_ENV_VARS)
def test_multiple_workers_is_a_violation(monkeypatch, name):
    monkeypatch.setenv(name, "4")
    reason = worker_count_violation()
    assert reason is not None
    assert name in reason
    assert "#120" in reason


@pytest.mark.parametrize("value", ["auto", "", "  ", "2.5", "N"])
def test_unparseable_worker_count(monkeypatch, value):
    """`WEB_CONCURRENCY=auto` is a scaling platform; blank/whitespace is unset."""
    monkeypatch.setenv("WEB_CONCURRENCY", value)
    reason = worker_count_violation()
    if value.strip():
        assert reason is not None, f"{value!r} should not be treated as single-worker"
    else:
        assert reason is None


def test_either_env_var_alone_trips_the_guard(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    monkeypatch.setenv("UVICORN_WORKERS", "8")
    assert worker_count_violation() is not None


def test_non_enforceable_assumptions_are_stated():
    """The replica/rolling-deploy half cannot be detected — it must be printed."""
    notes = " ".join(shared_state_warnings("local"))
    assert "replica" in notes
    assert "rolling" in notes
    assert "OAuth" in notes
    assert "S3" not in notes  # local backend → no object-storage caveat


def test_s3_append_caveat_only_on_s3():
    notes = " ".join(shared_state_warnings("s3"))
    assert "append" in notes and "lose data" in notes


# --- enforcement: startup ----------------------------------------------------


def test_create_app_refuses_multi_worker(monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        create_app()


def test_create_app_starts_single_worker(monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    assert create_app() is not None


# --- enforcement: doctor -----------------------------------------------------


def test_doctor_fails_on_multi_worker(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    doctor.check_runtime()
    assert doctor._fails >= 1


def test_doctor_passes_single_worker_but_warns_topology(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "storage_backend", "local")
    doctor.check_runtime()
    assert doctor._fails == 0
    # the platform-side obligations are never silently assumed
    assert doctor._warns >= 2


# --- why the contract exists: the process-local state ------------------------


def test_rate_limit_buckets_are_process_local():
    """N workers would give an attacker N× the budget (#120)."""
    from app.core.rate_limit import limiter

    limiter._read.clear()
    assert limiter._hit(limiter._read, "k", limit=1) is None  # 1st hit allowed
    assert limiter._hit(limiter._read, "k", limit=1) is not None  # 2nd throttled
    # The state lives on this module-level object, not in the DB or a cache
    # server, so a second process starts from an empty bucket.
    from app.core.rate_limit import RateLimiter

    assert RateLimiter()._hit(RateLimiter()._read, "k", limit=1) is None
    limiter._read.clear()


def test_local_control_token_is_process_local():
    """A token minted in one process is rejected by another (#120)."""
    from app.core.security import get_local_control_token

    assert get_local_control_token() == get_local_control_token()
    assert get_local_control_token()


def test_lan_switch_is_a_process_memory_mirror():
    """Turning LAN mode off only reaches the worker that served the write."""
    from app.services import settings_service

    assert hasattr(settings_service, "_lan_switch_cache")
    assert isinstance(settings_service.lan_switch_cached(), bool)


def test_oauth_state_is_shared_not_process_local():
    """#113 moved OAuth state to a DB row — the one piece #120 does NOT block on."""
    import inspect

    from app.services import oauth

    sig = inspect.signature(oauth.start_transaction)
    assert "session" in sig.parameters, "state must be persisted, not in-process"
    assert "session" in inspect.signature(oauth.consume_transaction).parameters


def test_s3_append_is_read_modify_write():
    """Lost-update window: no distributed lock, so one instance only (#120)."""
    import inspect

    from app.storage.s3 import S3Storage

    src = inspect.getsource(S3Storage.append_line)
    assert "read_bytes" in src and "write_bytes" in src
