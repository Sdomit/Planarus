"""Phase 10.6 go-live turnkey — the preflight doctor's checks.

Loads scripts/doctor.py by path (it's an ops script, not a package) and drives its
individual checks with monkeypatched settings, asserting the FAIL/OK accounting.
"""
import importlib.util
import pathlib

import pytest

from app.core.config import settings

_DOCTOR_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("planarus_doctor", _DOCTOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod  # fresh module → _fails/_warns start at 0


def test_dev_login_backdoor_is_a_failure(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    doctor.check_auth()
    assert doctor._fails >= 1


def test_auth_off_is_a_warning_not_failure(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "auth_enabled", False)
    doctor.check_auth()
    assert doctor._fails == 0
    assert doctor._warns >= 1


def test_oauth_missing_secret_fails(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "oauth_google_client_id", "abc")
    monkeypatch.setattr(settings, "oauth_google_client_secret", "")
    doctor.check_oauth()
    assert doctor._fails >= 1


def test_oauth_fully_configured_ok(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "oauth_github_client_id", "id")
    monkeypatch.setattr(settings, "oauth_github_client_secret", "secret")
    monkeypatch.setattr(settings, "oauth_google_client_id", "")
    monkeypatch.setattr(settings, "oauth_google_client_secret", "")
    doctor.check_oauth()
    assert doctor._fails == 0


def test_storage_local_ok_s3_missing_bucket_fails(monkeypatch):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "storage_backend", "local")
    doctor.check_storage()
    assert doctor._fails == 0

    doctor2 = _load_doctor()
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "storage_s3_bucket", "")
    doctor2.check_storage()
    assert doctor2._fails >= 1


def test_database_unmigrated_fails(monkeypatch, tmp_path):
    doctor = _load_doctor()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/empty.db")
    doctor.check_database()
    assert doctor._fails >= 1  # empty DB has no alembic revision
