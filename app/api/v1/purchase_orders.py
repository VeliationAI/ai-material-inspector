from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import PurchaseOrder, User
from app.db.session import get_db
from app.schemas import PurchaseOrderOut

router = APIRouter()


def _serialize(po: PurchaseOrder) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=po.id,
        po_number=po.po_number,
        sap_code=po.sap_code,
        material_name=po.material_name,
        material_category=po.material_category,
        manufacturer=po.manufacturer,
        manufacturer_aliases=[a for a in (po.manufacturer_aliases or "").split(",") if a],
        quantity=po.quantity,
        unit=po.unit,
        store=po.store,
        standard=po.standard,
        voltage_kv=po.voltage_kv,
        specs=json.loads(po.specs_json or "{}"),
        pilot_enabled=po.pilot_enabled,
    )


@router.get("", response_model=list[PurchaseOrderOut])
def list_pos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.organization_id == user.organization_id)
        .order_by(PurchaseOrder.po_number)
    ).all()
    return [_serialize(r) for r in rows]


@router.get("/{po_number}", response_model=PurchaseOrderOut)
def get_po(po_number: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == user.organization_id,
            PurchaseOrder.po_number == po_number,
        )
    )
    if not po:
        raise HTTPException(404, "Purchase order not found")
    return _serialize(po)
