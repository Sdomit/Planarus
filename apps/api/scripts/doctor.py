"""Preflight config check for a hosted Planarus deployment (Phase 10.6 turnkey).

Validates the environment BEFORE you boot the app — database reachable and
migrated, auth/tenancy configured sanely, each OAuth provider fully configured,
and (for the s3 backend) the bucket actually writable. Prints an OK/WARN/FAIL
checklist and exits non-zero if anything is a hard FAIL.

    cd apps/api && python scripts/doctor.py

Reads the same PLANARUS_* settings the app does; see deploy/hosted.env.example.
"""
import sys

from app.core.config import settings

_OK, _WARN, _FAIL = "  OK  ", " WARN ", " FAIL "
_fails = 0
_warns = 0


def _report(level: str, name: str, detail: str = "") -> None:
    global _fails, _warns
    if level == _FAIL:
        _fails += 1
    elif level == _WARN:
        _warns += 1
    print(f"[{level}] {name}" + (f" — {detail}" if detail else ""))


def check_database() -> None:
    try:
        from sqlalchemy import create_engine

        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            cfg = Config("alembic.ini")
            cfg.set_main_option("script_location", "alembic")
            heads = set(ScriptDirectory.from_config(cfg).get_heads())
            current = MigrationContext.configure(conn).get_current_revision()
        driver = settings.database_url.split(":", 1)[0]
        if current is None:
            _report(_FAIL, "database", f"connected ({driver}) but not migrated — run 'alembic upgrade head'")
        elif current not in heads:
            _report(_FAIL, "database", f"at {current}, not head {sorted(heads)} — run 'alembic upgrade head'")
        else:
            _report(_OK, "database", f"{driver}, schema at head ({current})")
    except Exception as exc:  # connection/driver error
        _report(_FAIL, "database", f"cannot connect: {exc}")


def check_auth() -> None:
    if not settings.auth_enabled:
        _report(_WARN, "auth", "PLANARUS_AUTH_ENABLED is off — single-user/local mode")
        return
    _report(_OK, "auth", "enabled")
    if settings.auth_dev_login_enabled:
        _report(_FAIL, "auth.dev_login", "dev-login is ON in an auth-enabled deploy — this is an unauthenticated account-creation backdoor; turn it OFF")
    if not settings.web_origins.strip():
        _report(_WARN, "auth.web_origins", "PLANARUS_WEB_ORIGINS is empty — the hosted frontend origin won't be allowed for login/CORS")


def check_oauth() -> None:
    providers = {
        "google": (settings.oauth_google_client_id, settings.oauth_google_client_secret),
        "github": (settings.oauth_github_client_id, settings.oauth_github_client_secret),
    }
    any_configured = False
    for name, (cid, secret) in providers.items():
        if not cid and not secret:
            continue
        any_configured = True
        if cid and secret:
            _report(_OK, f"oauth.{name}", "client id + secret set (verify the callback URL matches your OAuth app)")
        else:
            missing = "client secret" if cid else "client id"
            _report(_FAIL, f"oauth.{name}", f"{missing} is missing")
    if settings.auth_enabled and not any_configured and not settings.auth_dev_login_enabled:
        _report(_WARN, "oauth", "no OAuth provider configured and dev-login off — no way to sign in")


def check_storage() -> None:
    backend = settings.storage_backend
    if backend in ("local", "memory"):
        _report(_OK, "storage", f"{backend}")
        return
    if backend != "s3":
        _report(_FAIL, "storage", f"unknown backend {backend!r}")
        return
    if not settings.storage_s3_bucket:
        _report(_FAIL, "storage.s3", "PLANARUS_S3_BUCKET is not set")
        return
    try:
        import boto3  # noqa: F401
    except ImportError:
        _report(_WARN, "storage.s3", "boto3 not installed — install the [s3] extra to verify bucket access")
        return
    try:
        from app.storage.s3 import S3Storage

        store = S3Storage(
            bucket=settings.storage_s3_bucket,
            prefix=settings.storage_s3_prefix,
            region=settings.storage_s3_region or None,
            endpoint_url=settings.storage_s3_endpoint_url or None,
        )
        probe_root, probe_rel = "_doctor", "probe.txt"
        store.write_bytes(probe_root, probe_rel, b"ok")
        assert store.read_bytes(probe_root, probe_rel) == b"ok"
        # best-effort cleanup
        try:
            store._client.delete_object(
                Bucket=settings.storage_s3_bucket, Key=store._key(probe_root, probe_rel)
            )
        except Exception:
            pass
        _report(_OK, "storage.s3", f"bucket {settings.storage_s3_bucket!r} is writable")
    except Exception as exc:
        _report(_FAIL, "storage.s3", f"bucket not writable: {exc}")


def main() -> int:
    print("Planarus hosted preflight\n" + "=" * 24)
    check_database()
    check_auth()
    check_oauth()
    check_storage()
    print("-" * 24)
    if _fails:
        print(f"{_fails} failure(s), {_warns} warning(s) — resolve failures before going live.")
        return 1
    print(f"All checks passed ({_warns} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
