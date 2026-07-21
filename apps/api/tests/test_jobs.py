"""Phase 18.1 — the scheduled-job CLI (D41).

The contract that matters here is the **exit code**, because that is the only
thing cron / Task Scheduler / a systemd timer ever sees. A run that quietly
returns 0 while nothing was delivered is the exact failure D41 exists to prevent,
so each case below pins one code:

    0  work happened (or there was legitimately nothing to do)
    1  something genuinely broke — the scheduler should surface it
    2  refused on purpose — the feature is switched off

The SMTP client is faked at the ``email_service`` seam (no socket is opened) and
the database seam is the CLI's own ``_session``, pointed at a throwaway file DB.
"""
from contextlib import contextmanager
from email.message import EmailMessage

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import jobs
from app.core.config import settings as env
from app.core.utils import new_id, now_utc
from app.db.session import configure_sqlite_pragmas
from app.models.notification_rule import NotificationRule
from app.models.project import Project
from app.models.task import Task
from app.models.workspace import Workspace
from app.services import email_service, settings_service

_PAST = "2000-01-01T00:00:00+00:00"


# --- seams -------------------------------------------------------------------


class _FakeSMTP:
    sent: list[EmailMessage] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host, self.port = host, port

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def send_message(self, msg: EmailMessage) -> None:
        if _FakeSMTP.fail:
            raise ConnectionRefusedError("boom")
        _FakeSMTP.sent.append(msg)


@pytest.fixture(name="file_session")
def file_session_fixture(tmp_path):
    """A real on-disk SQLite database — what `backup` actually snapshots."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'planarus.db'}",
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_pragmas(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture(name="cli")
def cli_fixture(file_session, monkeypatch):
    """Point the CLI's single database seam at the throwaway file DB."""

    @contextmanager
    def _fake_session():
        yield file_session

    monkeypatch.setattr(jobs, "_session", _fake_session)
    return file_session


@pytest.fixture(name="backup_dir")
def backup_dir_fixture(tmp_path, monkeypatch):
    target = tmp_path / "backups"
    monkeypatch.setattr(env, "backup_dir", str(target))
    return target


@pytest.fixture(name="email_on")
def email_on_fixture(monkeypatch):
    """Enable email + fake the SMTP client. Restored automatically."""
    monkeypatch.setattr(env, "email_enabled", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []
    _FakeSMTP.fail = False
    yield
    _FakeSMTP.sent = []
    _FakeSMTP.fail = False


# --- seeding -----------------------------------------------------------------


def _seed_project(session, *, archived: bool = False) -> str:
    now = now_utc()
    ws = Workspace(
        id=new_id("ws"), name="WS", slug="ws-jobs", created_at=now, updated_at=now
    )
    session.add(ws)
    session.flush()
    proj = Project(
        id=new_id("proj"),
        workspace_id=ws.id,
        title="Jobs project",
        slug="p-jobs",
        status="idea",
        created_at=now,
        updated_at=now,
        archived_at=now if archived else None,
    )
    session.add(proj)
    session.commit()
    return proj.id


def _seed_rule(session, project_id: str) -> None:
    now = now_utc()
    session.add(
        NotificationRule(
            id=new_id("nrl"),
            project_id=project_id,
            channel="email",
            trigger_type="due_soon",
            enabled=True,
            to_email="me@example.com",
            threshold_hours=48,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _seed_overdue_task(session, project_id: str) -> None:
    now = now_utc()
    session.add(
        Task(
            id=new_id("task"),
            project_id=project_id,
            title="Overdue thing",
            status="todo",
            due_at=_PAST,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


# --- reminders ---------------------------------------------------------------


def test_reminders_refuses_when_email_is_switched_off(cli, capsys) -> None:
    """Off-by-default is a refusal (2), not a failure (1) — nothing is broken."""
    _seed_project(cli)
    assert jobs.main(["reminders"]) == jobs.EXIT_REFUSED
    assert "disabled" in capsys.readouterr().err.lower()


def test_reminders_sends_for_an_overdue_task(cli, email_on, capsys) -> None:
    pid = _seed_project(cli)
    _seed_rule(cli, pid)
    _seed_overdue_task(cli, pid)

    assert jobs.main(["reminders"]) == jobs.EXIT_OK
    assert len(_FakeSMTP.sent) == 1
    assert "sent 1" in capsys.readouterr().out


def test_reminders_exits_nonzero_when_a_send_fails(cli, email_on, capsys) -> None:
    """The reliability property: a broken pipeline must not report success.

    Individual rules fail without raising, so without an explicit check the job
    would exit 0 forever while no reminder ever arrived.
    """
    pid = _seed_project(cli)
    _seed_rule(cli, pid)
    _seed_overdue_task(cli, pid)
    _FakeSMTP.fail = True

    assert jobs.main(["reminders"]) == jobs.EXIT_FAILED
    assert "failed 1" in capsys.readouterr().out


def test_reminders_with_nothing_due_is_a_clean_run(cli, email_on, capsys) -> None:
    pid = _seed_project(cli)
    _seed_rule(cli, pid)  # a rule, but no task is due

    assert jobs.main(["reminders"]) == jobs.EXIT_OK
    assert _FakeSMTP.sent == []
    assert "skipped 1" in capsys.readouterr().out


def test_reminders_skips_archived_projects(cli, email_on, capsys) -> None:
    pid = _seed_project(cli, archived=True)
    _seed_rule(cli, pid)
    _seed_overdue_task(cli, pid)

    assert jobs.main(["reminders"]) == jobs.EXIT_OK
    assert _FakeSMTP.sent == []  # an archived project is not chased up
    assert "0 project(s)" in capsys.readouterr().out


# --- backup ------------------------------------------------------------------


def test_backup_refuses_when_switched_off(cli, backup_dir, capsys) -> None:
    assert jobs.main(["backup"]) == jobs.EXIT_REFUSED
    assert "disabled" in capsys.readouterr().err.lower()
    assert not backup_dir.exists()  # nothing written while switched off


def test_backup_writes_one_verified_snapshot(cli, backup_dir, capsys) -> None:
    _seed_project(cli)
    settings_service.set_setting(cli, "backup_enabled", True)
    cli.commit()

    assert jobs.main(["backup"]) == jobs.EXIT_OK
    written = list(backup_dir.iterdir())
    assert len(written) == 1
    assert written[0].name in capsys.readouterr().out


# --- argument handling -------------------------------------------------------


def test_a_missing_or_unknown_command_is_a_usage_error() -> None:
    """argparse exits 2 itself — no subcommand may silently do nothing."""
    with pytest.raises(SystemExit):
        jobs.main([])
    with pytest.raises(SystemExit):
        jobs.main(["definitely-not-a-command"])
