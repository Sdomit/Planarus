"""Idempotent regeneration of a project's `context/*` pack.

Per file: render -> checksum -> compare against the stored ContextFile row and
the on-disk bytes, then decide.

| condition                                   | action                        |
|---------------------------------------------|-------------------------------|
| row.pinned                                  | skip (never auto-overwrite)   |
| on-disk differs from last-written checksum  | drift: skip, mark manual edit |
| rendered == on-disk                         | unchanged: no write           |
| new / changed / missing file                | atomic write + upsert row     |

Each call writes one `context_regen` AuditEvent and appends one line to
`.agentboard/audit-log.jsonl`. The idempotency guarantee covers the `context/*`
files and `.agentboard/*.json` mirrors; the audit log is append-only by design.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.fsmemory import atomic_io
from app.fsmemory.locks import project_lock
from app.fsmemory.provisioner import provision_tree
from app.fsmemory.renderers import RenderContext, render
from app.fsmemory.spec import AUDIT_LOG_RELPATH, CONTEXT_FILES
from app.models.context_file import ContextFile
from app.models.project import Project
from app.models.workspace import Workspace
from app.services.audit_service import create_audit_event

STATUS_CREATED = "created"
STATUS_WRITTEN = "written"
STATUS_UNCHANGED = "unchanged"
STATUS_PINNED = "pinned-skip"
STATUS_DRIFT = "drift-skip"

_WROTE = {STATUS_CREATED, STATUS_WRITTEN}


@dataclass
class FileOutcome:
    relative_path: str
    kind: str
    status: str
    pinned: bool
    drifted: bool


@dataclass
class RegenReport:
    project_id: str
    generated_at: str
    outcomes: list[FileOutcome] = field(default_factory=list)

    @property
    def written_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status in _WROTE)

    @property
    def drifted_count(self) -> int:
        return sum(1 for o in self.outcomes if o.drifted)

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for o in self.outcomes:
            counts[o.status] = counts.get(o.status, 0) + 1
        return {
            "total": len(self.outcomes),
            "written": self.written_count,
            "drifted": self.drifted_count,
            "by_status": counts,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_updated_at(project: Project, workspace: Workspace) -> str:
    # Both timestamps are UTC ISO-8601 (+00:00), so a lexicographic max is valid.
    return max(project.updated_at, workspace.updated_at)


def regenerate(
    session: Session,
    project: Project,
    workspace: Workspace,
    *,
    now: str | None = None,
    actor_type: str = "human",
) -> RegenReport:
    """Provision the folder and regenerate the context pack. DB + disk in sync."""
    root = project.folder_path
    if not root:
        raise ValueError("project has no folder_path")

    now = now or now_utc()
    ctx = RenderContext(
        project=project,
        workspace=workspace,
        updated_at=_content_updated_at(project, workspace),
    )
    report = RegenReport(project_id=project.id, generated_at=now)

    with project_lock(root):
        provision_tree(root, project, workspace)

        existing = {
            cf.relative_path: cf
            for cf in session.exec(
                select(ContextFile).where(ContextFile.project_id == project.id)
            ).all()
        }

        for spec in CONTEXT_FILES:
            rel = spec.relative_path
            rendered = render(spec, ctx)
            rendered_sum = _sha256(rendered.encode("utf-8"))
            row = existing.get(rel)

            on_disk = atomic_io.read_bytes(root, rel)
            on_disk_sum = _sha256(on_disk) if on_disk is not None else None

            pinned = bool(row.pinned) if row is not None else False
            drifted = (
                row is not None
                and on_disk_sum is not None
                and on_disk_sum != row.checksum
            )

            if pinned:
                report.outcomes.append(
                    FileOutcome(rel, spec.kind, STATUS_PINNED, True, drifted)
                )
                continue

            if drifted:
                row.last_manual_edit_at = now
                row.updated_at = now
                session.add(row)
                report.outcomes.append(
                    FileOutcome(rel, spec.kind, STATUS_DRIFT, False, True)
                )
                continue

            if row is not None and on_disk_sum == rendered_sum:
                report.outcomes.append(
                    FileOutcome(rel, spec.kind, STATUS_UNCHANGED, False, False)
                )
                continue

            # New row, changed content, or a missing file: write and upsert.
            atomic_io.write_text(root, rel, rendered)
            token_estimate = max(1, len(rendered) // 4)
            if row is None:
                session.add(
                    ContextFile(
                        id=new_id("ctx"),
                        project_id=project.id,
                        kind=spec.kind,
                        relative_path=rel,
                        checksum=rendered_sum,
                        generated_at=now,
                        pinned=False,
                        last_manual_edit_at=None,
                        token_estimate=token_estimate,
                        created_at=now,
                        updated_at=now,
                    )
                )
                report.outcomes.append(
                    FileOutcome(rel, spec.kind, STATUS_CREATED, False, False)
                )
            else:
                row.checksum = rendered_sum
                row.generated_at = now
                row.token_estimate = token_estimate
                row.last_manual_edit_at = None
                row.updated_at = now
                session.add(row)
                report.outcomes.append(
                    FileOutcome(rel, spec.kind, STATUS_WRITTEN, False, False)
                )

        event = create_audit_event(
            session,
            event_type="context_regen",
            actor_type=actor_type,
            entity_type="project",
            entity_id=project.id,
            workspace_id=project.workspace_id,
            project_id=project.id,
            payload_json=json.dumps(report.summary(), sort_keys=True),
        )
        atomic_io.append_jsonl(
            root,
            AUDIT_LOG_RELPATH,
            {
                "id": event.id,
                "event_type": "context_regen",
                "project_id": project.id,
                "created_at": event.created_at,
                "summary": report.summary(),
            },
        )

    return report
