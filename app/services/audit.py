from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record(
    db: Session,
    *,
    organization_id: int,
    action: str,
    user_id: int | None = None,
    entity_type: str = "",
    entity_id: str = "",
    detail: str = "",
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )
