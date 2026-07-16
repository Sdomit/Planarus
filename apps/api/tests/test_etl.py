"""Phase 10.5 — application-level DB ETL (copy_all).

Exercises FK-ordered copy, the non-empty-target guardrail, and row-count
verification with two SQLite databases (hermetic). The cross-dialect
SQLite→Postgres path (the real use case) is verified manually against a live
Postgres 16 — see the phase doc — since CI can't assume a Postgres service here.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.etl import EtlError, copy_all
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.project import ProjectCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import project_service, workspace_service


def _make_db(path):
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    return url, engine


def _seed(engine, slug):
    with Session(engine) as s:
        ws = workspace_service.create_workspace(
            s, WorkspaceCreate(name=slug, slug=slug)
        )
        project_service.create_project(
            s, ProjectCreate(workspace_id=ws.id, title="P", slug=f"{slug}p")
        )
        return ws.id


def test_copy_all_roundtrip_and_verify(tmp_path):
    src_url, src_eng = _make_db(tmp_path / "src.db")
    tgt_url, tgt_eng = _make_db(tmp_path / "tgt.db")
    _seed(src_eng, "acme")

    report = copy_all(src_url, tgt_url)
    assert report["workspace"] == 1
    assert report["project"] == 1
    assert report["auditevent"] >= 1  # create wrote audit rows

    # FK order held and rows actually landed in the target.
    with Session(tgt_eng) as t:
        assert len(t.exec(select(Workspace)).all()) == 1
        projects = t.exec(select(Project)).all()
        assert len(projects) == 1
        assert projects[0].title == "P"


def test_guardrail_refuses_nonempty_target(tmp_path):
    src_url, src_eng = _make_db(tmp_path / "src.db")
    tgt_url, tgt_eng = _make_db(tmp_path / "tgt.db")
    _seed(src_eng, "acme")
    _seed(tgt_eng, "other")  # target already has data

    with pytest.raises(EtlError, match="non-empty target"):
        copy_all(src_url, tgt_url)

    # Explicit override is allowed (though it may then hit PK collisions — the
    # guardrail exists precisely so this is a deliberate act).
    # We only assert the guardrail is what blocked the default call above.


def test_same_source_and_target_rejected(tmp_path):
    url, _ = _make_db(tmp_path / "one.db")
    with pytest.raises(EtlError, match="must differ"):
        copy_all(url, url)


def test_empty_source_copies_zero(tmp_path):
    src_url, _ = _make_db(tmp_path / "src.db")
    tgt_url, _ = _make_db(tmp_path / "tgt.db")
    report = copy_all(src_url, tgt_url)
    assert set(report.values()) == {0}
