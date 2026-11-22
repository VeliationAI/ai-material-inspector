from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Organization, PurchaseOrder, Role, User
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_org_and_users(db)
        _ensure_purchase_orders(db)
        db.commit()
    finally:
        db.close()


def _ensure_org_and_users(db: Session) -> None:
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.name == settings.default_org_name))
    if not org:
        org = Organization(name=settings.default_org_name)
        db.add(org)
        db.flush()
        logger.info("Created organization %s", org.name)

    user = db.scalar(select(User).where(User.email == settings.default_admin_email))
    if not user:
        db.add(
            User(
                organization_id=org.id,
                email=settings.default_admin_email,
                full_name="Store Officer Demo",
                hashed_password=hash_password(settings.default_admin_password),
                role=Role.admin,
            )
        )
        logger.info("Seeded demo officer %s", settings.default_admin_email)


def _ensure_purchase_orders(db: Session) -> None:
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.name == settings.default_org_name))
    if not org:
        return
    count = db.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.organization_id == org.id))
    if count and count > 0:
        return

    payload = json.loads(settings.sample_pos_path.read_text(encoding="utf-8"))
    for row in payload:
        db.add(
            PurchaseOrder(
                organization_id=org.id,
                po_number=row["po_number"],
                sap_code=row["sap_code"],
                material_name=row["material_name"],
                material_category=row.get("material_category", "insulator"),
                manufacturer=row["manufacturer"],
                manufacturer_aliases=",".join(row.get("manufacturer_aliases") or []),
                quantity=row.get("quantity", 1),
                unit=row.get("unit", "EA"),
                store=row.get("store", ""),
                standard=row.get("standard", ""),
                voltage_kv=row.get("voltage_kv"),
                specs_json=json.dumps(row.get("specs") or {}),
                pilot_enabled=bool(row.get("pilot_enabled", True)),
            )
        )
    logger.info("Seeded %s sample purchase orders", len(payload))
