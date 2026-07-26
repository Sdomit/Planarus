"""#92: offset paging on the agent read surfaces, and the get_item detail tool.

Before this, every list tool capped at MAX_LIST_ROWS with no offset, so rows past
the cap were unreachable through any agent surface; get_doc_excerpt reported
full_length but could not read past max_chars; and no tool returned a field above
the 500-char list clip, so an agent shown "truncated, N more chars" had to either
guess or propose an edit from a clipped value.
"""
import re

import pytest
from app.mcp import errors
from app.mcp.serializers import MAX_DETAIL_CHARS, MAX_FIELD_CHARS
from app.mcp.tools import read
from app.schemas.decision import DecisionCreate
from app.schemas.doc import DocCreate, DocUpdate
from app.schemas.risk import RiskCreate
from app.schemas.task import TaskCreate
from app.services import decision_service, doc_service, risk_service, task_service
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.mcp_util import read_cap, seed


def _make_tasks(session: Session, pid: str, n: int) -> None:
    for i in range(n):
        task_service.create_task(session, pid, TaskCreate(title=f"task {i:03d}"))


# --- list paging -------------------------------------------------------------


def test_offset_reaches_rows_past_the_first_page(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "pg1")
    _make_tasks(session, pid, 7)
    cap = read_cap(ws, pid)

    first = read.list_tasks(session, cap, read.ListTasksArgs(project_id=pid, limit=3))
    assert first.metadata["count"] == 3
    assert first.metadata["offset"] == 0
    assert first.metadata["row_truncated"] is True
    assert first.metadata["next_offset"] == 3

    second = read.list_tasks(
        session, cap, read.ListTasksArgs(project_id=pid, limit=3, offset=3)
    )
    assert second.metadata["offset"] == 3
    assert second.metadata["next_offset"] == 6
    # Disjoint pages: nothing from page 1 reappears on page 2.
    assert "task 002" in first.text and "task 002" not in second.text
    assert "task 003" in second.text and "task 003" not in first.text


def test_last_page_reports_no_next_offset(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pg2")
    _make_tasks(session, pid, 5)
    cap = read_cap(ws, pid)

    last = read.list_tasks(
        session, cap, read.ListTasksArgs(project_id=pid, limit=3, offset=3)
    )
    assert last.metadata["count"] == 2
    assert last.metadata["row_truncated"] is False
    assert last.metadata["next_offset"] is None


def test_paging_walks_every_row_exactly_once(
    client: TestClient, session: Session
) -> None:
    """The whole point: no row is unreachable, and none is served twice."""
    ws, pid = seed(client, "pg3")
    _make_tasks(session, pid, 11)
    cap = read_cap(ws, pid)

    seen: list[str] = []
    offset, pages = 0, 0
    while True:
        res = read.list_tasks(
            session, cap, read.ListTasksArgs(project_id=pid, limit=4, offset=offset)
        )
        seen.extend(res.metadata["statuses"])
        pages += 1
        if res.metadata["next_offset"] is None:
            break
        offset = res.metadata["next_offset"]
        assert pages < 10, "paging failed to terminate"

    assert len(seen) == 11


def test_offset_rejects_negative(client: TestClient, session: Session) -> None:
    with pytest.raises(Exception):
        read.ListTasksArgs(project_id="p", offset=-1)


@pytest.mark.parametrize(
    "idx,tool,args_cls",
    [
        (0, read.list_decisions, read.ListPhaseScopedArgs),
        (1, read.list_risks, read.ListPhaseScopedArgs),
        (2, read.list_docs, read.ListScopedArgs),
    ],
)
def test_every_list_tool_exposes_paging_scalars(
    client: TestClient, session: Session, idx: int, tool, args_cls
) -> None:
    ws, pid = seed(client, f"pg4x{idx}")
    cap = read_cap(ws, pid)
    res = tool(session, cap, args_cls(project_id=pid))
    for key in ("limit", "offset", "row_truncated", "next_offset"):
        assert key in res.metadata, f"{tool.__name__} missing {key}"


def test_decisions_and_risks_page_independently(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "pg5")
    for i in range(4):
        decision_service.create_decision(
            session, pid, DecisionCreate(title=f"d{i}", decision=f"do {i}")
        )
        risk_service.create_risk(
            session, pid, RiskCreate(title=f"r{i}", severity="low")
        )
    cap = read_cap(ws, pid)

    d = read.list_decisions(
        session, cap, read.ListPhaseScopedArgs(project_id=pid, limit=2, offset=2)
    )
    r = read.list_risks(
        session, cap, read.ListPhaseScopedArgs(project_id=pid, limit=2, offset=2)
    )
    assert d.metadata["count"] == 2 and d.metadata["next_offset"] is None
    assert r.metadata["count"] == 2 and r.metadata["next_offset"] is None


# --- doc excerpt paging ------------------------------------------------------


def _doc_with_body(session: Session, pid: str, body: str) -> str:
    doc = doc_service.create_doc(session, pid, DocCreate(title="Big", doc_type="note"))
    doc_service.update_doc(
        session,
        doc.id,
        DocUpdate(version=doc.version, content_json='{"type":"doc"}', markdown_cache=body),
    )
    return doc.id


def test_doc_excerpt_offset_reaches_the_tail(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "pg6")
    body = "A" * 4000 + "B" * 4000 + "TAIL_MARKER"
    doc_id = _doc_with_body(session, pid, body)
    cap = read_cap(ws, pid)

    first = read.get_doc_excerpt(session, cap, read.DocExcerptArgs(doc_id=doc_id))
    assert first.metadata["offset"] == 0
    assert first.metadata["full_length"] == len(body)
    assert first.metadata["next_offset"] == 4000
    assert "TAIL_MARKER" not in first.text

    # Walk to the end; the marker was previously unreachable through any surface.
    offset, text = first.metadata["next_offset"], ""
    for _ in range(5):
        page = read.get_doc_excerpt(
            session, cap, read.DocExcerptArgs(doc_id=doc_id, offset=offset)
        )
        text += page.text
        if page.metadata["next_offset"] is None:
            break
        offset = page.metadata["next_offset"]
    assert "TAIL_MARKER" in text


def test_doc_excerpt_offset_past_end_is_empty_not_an_error(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "pg7")
    doc_id = _doc_with_body(session, pid, "short body")
    cap = read_cap(ws, pid)

    res = read.get_doc_excerpt(
        session, cap, read.DocExcerptArgs(doc_id=doc_id, offset=9999)
    )
    assert res.metadata["excerpt_length"] == 0
    assert res.metadata["next_offset"] is None


def test_doc_excerpt_still_marks_truncation_in_text(
    client: TestClient, session: Session
) -> None:
    """The in-text marker must survive the offset change, with a true remainder."""
    ws, pid = seed(client, "pg8")
    doc_id = _doc_with_body(session, pid, "X" * 9000)
    cap = read_cap(ws, pid)

    res = read.get_doc_excerpt(
        session, cap, read.DocExcerptArgs(doc_id=doc_id, max_chars=4000)
    )
    assert "(truncated, 5000 more chars)" in res.text


# --- get_item ----------------------------------------------------------------


def test_get_item_returns_field_above_the_list_clip(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "pg9")
    long_desc = "D" * 1800  # over MAX_FIELD_CHARS, under MAX_DETAIL_CHARS
    task = task_service.create_task(
        session, pid, TaskCreate(title="Detailed", description=long_desc)
    )
    cap = read_cap(ws, pid)

    listed = read.list_tasks(session, cap, read.ListTasksArgs(project_id=pid))
    assert listed.metadata["field_truncated"] is True
    assert "D" * (MAX_FIELD_CHARS + 1) not in listed.text

    detail = read.get_item(
        session, cap, read.GetItemArgs(kind="task", item_id=task.id)
    )
    assert detail.metadata["kind"] == "task"
    assert detail.metadata["max_chars"] == MAX_DETAIL_CHARS
    assert long_desc in detail.text


@pytest.mark.parametrize("kind", ["task", "decision", "risk", "doc"])
def test_get_item_supports_every_declared_kind(
    client: TestClient, session: Session, kind: str
) -> None:
    ws, pid = seed(client, f"pg10{kind[:4]}")
    makers = {
        "task": lambda: task_service.create_task(session, pid, TaskCreate(title="T")),
        "decision": lambda: decision_service.create_decision(
            session, pid, DecisionCreate(title="D", decision="do it")
        ),
        "risk": lambda: risk_service.create_risk(
            session, pid, RiskCreate(title="R", severity="low")
        ),
        "doc": lambda: doc_service.create_doc(
            session, pid, DocCreate(title="Doc", doc_type="note")
        ),
    }
    obj = makers[kind]()
    cap = read_cap(ws, pid)

    res = read.get_item(session, cap, read.GetItemArgs(kind=kind, item_id=obj.id))
    assert res.metadata["item_id"] == obj.id
    assert res.metadata["project_id"] == pid


def test_get_item_is_scope_checked(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pg11")
    _, other_pid = seed(client, "pg12")
    foreign = task_service.create_task(session, other_pid, TaskCreate(title="Secret"))
    cap = read_cap(ws, pid)

    with pytest.raises(errors.MCPToolError) as e:
        read.get_item(session, cap, read.GetItemArgs(kind="task", item_id=foreign.id))
    # Generic not_found, not forbidden — must not reveal that the row exists.
    assert e.value.code == errors.CODE_NOT_FOUND


def test_get_item_missing_id_is_not_found(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "pg13")
    cap = read_cap(ws, pid)
    with pytest.raises(errors.MCPToolError) as e:
        read.get_item(session, cap, read.GetItemArgs(kind="task", item_id="task_nope"))
    assert e.value.code == errors.CODE_NOT_FOUND


def test_get_item_rejects_unknown_kind(client: TestClient, session: Session) -> None:
    with pytest.raises(Exception):
        read.GetItemArgs(kind="workspace", item_id="x")


# --- #153 review findings -----------------------------------------------------


@pytest.mark.parametrize(
    "idx,kind,meta_key",
    [(0, "task", "task_ids"), (1, "decision", "decision_ids"), (2, "risk", "risk_ids")],
)
def test_list_supplies_the_id_get_item_needs(
    client: TestClient, session: Session, idx: int, kind: str, meta_key: str
) -> None:
    """The list -> get_item handoff. Ids in block text come back entropy-masked,
    so without an id array in metadata get_item cannot be called at all."""
    ws, pid = seed(client, f"rv1x{idx}")
    makers = {
        "task": lambda: task_service.create_task(session, pid, TaskCreate(title="T")),
        "decision": lambda: decision_service.create_decision(
            session, pid, DecisionCreate(title="D", decision="do it")
        ),
        "risk": lambda: risk_service.create_risk(
            session, pid, RiskCreate(title="R", severity="low")
        ),
    }
    obj = makers[kind]()
    cap = read_cap(ws, pid)
    listers = {
        "task": lambda: read.list_tasks(session, cap, read.ListTasksArgs(project_id=pid)),
        "decision": lambda: read.list_decisions(
            session, cap, read.ListPhaseScopedArgs(project_id=pid)
        ),
        "risk": lambda: read.list_risks(
            session, cap, read.ListPhaseScopedArgs(project_id=pid)
        ),
    }
    listed = listers[kind]()

    assert listed.metadata[meta_key] == [obj.id]
    # The id must be usable verbatim — this is the whole point.
    detail = read.get_item(
        session, cap, read.GetItemArgs(kind=kind, item_id=listed.metadata[meta_key][0])
    )
    assert detail.metadata["item_id"] == obj.id


def test_risk_mitigation_is_reachable(client: TestClient, session: Session) -> None:
    """list_risks omits it, so get_item was its only possible route — and didn't."""
    ws, pid = seed(client, "rv2")
    risk = risk_service.create_risk(
        session,
        pid,
        RiskCreate(title="R", severity="high", mitigation="Fail closed and page on-call"),
    )
    res = read.get_item(session, read_cap(ws, pid), read.GetItemArgs(kind="risk", item_id=risk.id))
    assert "Fail closed and page on-call" in res.text


def test_doc_excerpt_paging_reconstructs_the_whole_document(
    client: TestClient, session: Session
) -> None:
    """The invariant: concatenating every page must equal the redacted document
    exactly — no gap, no repeat.

    Offsets used to be counted on raw text while the page rendered
    redacted-then-clipped text. A placeholder is a different length from the span
    it replaces, so each page containing a secret consumed fewer raw characters
    than the offset advanced by, silently skipping the difference. Asserting that
    one marker survives is too weak to catch that — whether it lands in a skipped
    window is luck. Reconstruction is not.
    """
    from app.mcp.serializers import redact

    ws, pid = seed(client, "rv3")
    # Padding must not merge into the token: a run of "A" immediately before
    # "AKIA..." defeats the detector's word boundary and nothing gets masked.
    body = ("word " * 6 + "AKIAIOSFODNN7EXAMPLE" + " filler" * 4) * 3 + " END"
    doc_id = _doc_with_body(session, pid, body)
    cap = read_cap(ws, pid)

    expected, _ = redact(body)
    assert "«redacted:" in expected, "test data must actually trigger redaction"

    rebuilt, offset = "", 0
    for _ in range(60):
        page = read.get_doc_excerpt(
            session, cap, read.DocExcerptArgs(doc_id=doc_id, max_chars=40, offset=offset)
        )
        line = next(x for x in page.text.splitlines() if x.startswith("excerpt: "))
        rebuilt += re.sub(r" \u2026\(truncated, \d+ more chars\)$", "", line[len("excerpt: "):])
        if page.metadata["next_offset"] is None:
            break
        offset = page.metadata["next_offset"]

    assert rebuilt == expected, "paging did not reproduce the document exactly"
    assert "AKIAIOSFODNN7EXAMPLE" not in rebuilt
