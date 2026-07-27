from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.mention import MentionRead
from app.services import mention_service
from app.services.entity_registry import titles_for

router = APIRouter()


@router.get("/projects/{project_id}/mentions", response_model=list[MentionRead])
def list_mentions(
    project_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    source_doc_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[MentionRead]:
    rows = mention_service.list_mentions(
        session,
        project_id,
        target_type=target_type,
        target_id=target_id,
        source_doc_id=source_doc_id,
    )
    # One batched query for every distinct source doc, not one per row — a
    # "Referenced by" panel with a dozen backlinks stays a single extra query.
    # Explicitly project-scoped: the ids are already confined to this project by
    # `list_mentions`, but a title lookup is not the place to rely on a caller's
    # filtering staying correct.
    titles = titles_for(
        session, {"doc": {m.source_doc_id for m in rows}}, project_id=project_id
    )
    result: list[MentionRead] = []
    for m in rows:
        item = MentionRead.model_validate(m)
        item.source_doc_title = titles.get(("doc", m.source_doc_id))
        result.append(item)
    return result
