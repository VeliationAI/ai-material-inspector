from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.models import ApprovalStatus, Decision, Inspection, InspectionImage, PurchaseOrder, User
from app.db.session import get_db
from app.schemas import ApprovalRequest, FindingOut, ImageOut, InspectionOut
from app.services.audit import record
from app.services.pipeline import run_pipeline
from app.services.rules import decision_label

router = APIRouter()


def _serialize(insp: Inspection) -> InspectionOut:
    po = insp.purchase_order
    return InspectionOut(
        id=insp.id,
        purchase_order_id=insp.purchase_order_id,
        po_number=po.po_number if po else "",
        material_name=po.material_name if po else "",
        ai_decision=decision_label(insp.ai_decision),
        approval_status=insp.approval_status.value,
        narrative=insp.narrative,
        summary=json.loads(insp.summary_json or "{}"),
        measured_creepage_mm=insp.measured_creepage_mm,
        measured_height_mm=insp.measured_height_mm,
        measured_diameter_mm=insp.measured_diameter_mm,
        findings=[
            FindingOut(
                check_name=f.check_name,
                result=f.result,
                detail=f.detail,
                severity=f.severity,
            )
            for f in insp.findings
        ],
        images=[
            ImageOut(
                id=img.id,
                angle=img.angle,
                path=f"/api/v1/inspections/{insp.id}/images/{img.id}",
                annotated_path=(
                    f"/api/v1/inspections/{insp.id}/images/{img.id}/annotated"
                    if img.annotated_path
                    else None
                ),
                ocr_text=img.ocr_text or "",
            )
            for img in insp.images
        ],
        report_available=bool(insp.report_path),
        created_at=insp.created_at,
    )


@router.get("", response_model=list[InspectionOut])
def list_inspections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Inspection)
        .options(joinedload(Inspection.purchase_order), joinedload(Inspection.images), joinedload(Inspection.findings))
        .where(Inspection.organization_id == user.organization_id)
        .order_by(Inspection.id.desc())
        .limit(50)
    ).unique().all()
    return [_serialize(r) for r in rows]


@router.get("/{inspection_id}", response_model=InspectionOut)
def get_inspection(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _load(db, user, inspection_id)
    return _serialize(insp)


@router.post("", response_model=InspectionOut)
async def create_inspection(
    po_number: str = Form(...),
    measured_creepage_mm: float | None = Form(None),
    measured_height_mm: float | None = Form(None),
    measured_diameter_mm: float | None = Form(None),
    notes: str = Form(""),
    angles: str = Form("front,side,label"),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "At least one image is required")
    if len(files) > 8:
        raise HTTPException(400, "Maximum 8 images per inspection")

    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == user.organization_id,
            PurchaseOrder.po_number == po_number,
        )
    )
    if not po:
        raise HTTPException(404, "Purchase order not found")
    if not po.pilot_enabled:
        raise HTTPException(400, "This material category is not enabled for the CV pilot yet")

    settings = get_settings()
    insp = Inspection(
        organization_id=user.organization_id,
        purchase_order_id=po.id,
        created_by_id=user.id,
        measured_creepage_mm=measured_creepage_mm,
        measured_height_mm=measured_height_mm,
        measured_diameter_mm=measured_diameter_mm,
        notes=notes or "",
        ai_decision=Decision.pending,
        approval_status=ApprovalStatus.pending,
    )
    db.add(insp)
    db.flush()

    angle_list = [a.strip() or "front" for a in angles.split(",")]
    for idx, upload in enumerate(files):
        content = await upload.read()
        if not content:
            continue
        ext = Path(upload.filename or "photo.jpg").suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            ext = ".jpg"
        dest = settings.upload_dir / f"insp_{insp.id}_{uuid.uuid4().hex}{ext}"
        dest.write_bytes(content)
        angle = angle_list[idx] if idx < len(angle_list) else f"view_{idx + 1}"
        db.add(InspectionImage(inspection_id=insp.id, angle=angle, path=str(dest)))

    db.flush()
    insp = db.scalar(
        select(Inspection)
        .options(joinedload(Inspection.images), joinedload(Inspection.findings), joinedload(Inspection.purchase_order))
        .where(Inspection.id == insp.id)
    )
    assert insp is not None
    run_pipeline(db, insp, po)
    record(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="inspection_created",
        entity_type="inspection",
        entity_id=str(insp.id),
        detail=decision_label(insp.ai_decision),
    )
    db.commit()
    db.refresh(insp)
    insp = _load(db, user, insp.id)
    return _serialize(insp)


@router.post("/{inspection_id}/approve", response_model=InspectionOut)
def approve_inspection(
    inspection_id: int,
    payload: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    insp = _load(db, user, inspection_id)
    insp.approval_status = ApprovalStatus.approved if payload.approve else ApprovalStatus.rejected
    insp.approved_by_id = user.id
    insp.approved_at = datetime.now(timezone.utc)
    if payload.notes:
        insp.notes = (insp.notes + "\n" + payload.notes).strip()
    record(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="inspection_approved" if payload.approve else "inspection_rejected",
        entity_type="inspection",
        entity_id=str(insp.id),
        detail=payload.notes or insp.approval_status.value,
    )
    db.commit()
    return _serialize(_load(db, user, inspection_id))


@router.get("/{inspection_id}/report")
def download_report(inspection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _load(db, user, inspection_id)
    if not insp.report_path or not Path(insp.report_path).exists():
        raise HTTPException(404, "Report not available")
    return FileResponse(
        insp.report_path,
        media_type="application/pdf",
        filename=f"inspection_{inspection_id}.pdf",
    )


@router.get("/{inspection_id}/images/{image_id}")
def get_image(inspection_id: int, image_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _load(db, user, inspection_id)
    image = next((i for i in insp.images if i.id == image_id), None)
    if not image or not Path(image.path).exists():
        raise HTTPException(404, "Image not found")
    return FileResponse(image.path)


@router.get("/{inspection_id}/images/{image_id}/annotated")
def get_annotated(inspection_id: int, image_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    insp = _load(db, user, inspection_id)
    image = next((i for i in insp.images if i.id == image_id), None)
    if not image or not image.annotated_path or not Path(image.annotated_path).exists():
        raise HTTPException(404, "Annotated image not found")
    return FileResponse(image.annotated_path)


def _load(db: Session, user: User, inspection_id: int) -> Inspection:
    insp = db.scalar(
        select(Inspection)
        .options(joinedload(Inspection.purchase_order), joinedload(Inspection.images), joinedload(Inspection.findings))
        .where(Inspection.id == inspection_id, Inspection.organization_id == user.organization_id)
    )
    if not insp:
        raise HTTPException(404, "Inspection not found")
    return insp
