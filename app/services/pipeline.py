"""Orchestrate vision + OCR + rules for an inspection."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Finding, Inspection, InspectionImage, PurchaseOrder
from app.services import ocr as ocr_svc
from app.services import rules
from app.services import vision
from app.services.report_pdf import build_report


def po_to_dict(po: PurchaseOrder) -> dict[str, Any]:
    return {
        "id": po.id,
        "po_number": po.po_number,
        "sap_code": po.sap_code,
        "material_name": po.material_name,
        "material_category": po.material_category,
        "manufacturer": po.manufacturer,
        "manufacturer_aliases": [a for a in (po.manufacturer_aliases or "").split(",") if a],
        "quantity": po.quantity,
        "unit": po.unit,
        "store": po.store,
        "standard": po.standard,
        "voltage_kv": po.voltage_kv,
        "specs": json.loads(po.specs_json or "{}"),
        "pilot_enabled": po.pilot_enabled,
    }


def run_pipeline(db: Session, inspection: Inspection, po: PurchaseOrder) -> Inspection:
    settings = get_settings()
    all_defects: list[dict[str, Any]] = []
    ocr_texts: list[str] = []
    ocr_parsed: dict[str, Any] = {}
    annotated_paths: list[str] = []

    for image in inspection.images:
        src = Path(image.path)
        ann = settings.annotated_dir / f"insp_{inspection.id}_{image.id}_{uuid.uuid4().hex[:8]}.jpg"
        vision_result = vision.analyze_image(src, ann)
        if vision_result.get("annotated_path"):
            image.annotated_path = vision_result["annotated_path"]
            annotated_paths.append(vision_result["annotated_path"])
        all_defects.extend(vision_result.get("defects") or [])

        ocr_result = ocr_svc.extract_text(src)
        image.ocr_text = ocr_result.get("raw_text") or ""
        if image.ocr_text:
            ocr_texts.append(image.ocr_text)
        for key, value in (ocr_result.get("parsed") or {}).items():
            if value and not ocr_parsed.get(key):
                ocr_parsed[key] = value

    combined_ocr = {
        "raw_text": "\n".join(ocr_texts),
        "parsed": ocr_parsed,
        "engine": "rapidocr" if ocr_texts else "unavailable",
    }
    measured = {
        "creepage_mm": inspection.measured_creepage_mm,
        "height_mm": inspection.measured_height_mm,
        "diameter_mm": inspection.measured_diameter_mm,
    }
    evaluation = rules.evaluate_inspection(
        po=po_to_dict(po),
        photo_count=len(inspection.images),
        defects=all_defects,
        ocr=combined_ocr,
        measured=measured,
    )

    inspection.findings.clear()
    for check in evaluation["checks"]:
        inspection.findings.append(
            Finding(
                check_name=check["check_name"],
                result=check["result"],
                detail=check["detail"],
                severity=check.get("severity", "info"),
                evidence_json=json.dumps({"defects": all_defects} if check["check_name"] == "surface_defects" else {}),
            )
        )

    inspection.ai_decision = evaluation["decision"]
    inspection.narrative = evaluation["narrative"]
    summary = {
        "decision": rules.decision_label(evaluation["decision"]),
        "failed_checks": evaluation["failed_checks"],
        "review_checks": evaluation["review_checks"],
        "defect_count": evaluation["defect_count"],
        "ocr_parsed": evaluation["ocr_parsed"],
        "manufacturer_match": evaluation["manufacturer_match"],
        "defects": all_defects,
    }
    inspection.summary_json = json.dumps(summary)

    report_path = settings.reports_dir / f"inspection_{inspection.id}.pdf"
    build_report(
        report_path,
        {
            "decision_label": summary["decision"],
            "narrative": inspection.narrative,
            "purchase_order": po_to_dict(po),
            "checks": evaluation["checks"],
            "measured": measured,
            "annotated_images": annotated_paths,
        },
    )
    inspection.report_path = str(report_path)
    db.add(inspection)
    db.flush()
    return inspection
