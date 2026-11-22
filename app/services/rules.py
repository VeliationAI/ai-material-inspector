"""Deterministic PO conformity rules. LLM/narrative is explanatory only."""

from __future__ import annotations

import json
from typing import Any

from app.db.models import Decision


def _check(name: str, passed: bool, detail: str, severity: str = "info") -> dict[str, Any]:
    return {
        "check_name": name,
        "result": "PASS" if passed else "FAIL",
        "detail": detail,
        "severity": severity if not passed else "info",
    }


def evaluate_inspection(
    *,
    po: dict[str, Any],
    photo_count: int,
    defects: list[dict[str, Any]],
    ocr: dict[str, Any],
    measured: dict[str, float | None],
) -> dict[str, Any]:
    specs = po.get("specs") or {}
    aliases = po.get("manufacturer_aliases") or []
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.split(",") if a.strip()]

    raw_text = ocr.get("raw_text") or ""
    mfr = _manufacturer_ok(raw_text, po.get("manufacturer", ""), aliases)
    parsed = ocr.get("parsed") or {}

    checks: list[dict[str, Any]] = [
        _check(
            "photo_evidence",
            photo_count >= 2,
            f"{photo_count} photo(s) uploaded, minimum 2 required",
            "high",
        ),
        _check(
            "material_identity",
            po.get("material_category") == "insulator" and bool(po.get("pilot_enabled", True)),
            "Pilot SKU is porcelain insulator" if po.get("pilot_enabled") else "Material category not enabled for CV pilot",
            "high",
        ),
        _check(
            "manufacturer_ocr",
            mfr["matched"] or not raw_text,
            (
                f"OCR matched manufacturer: {', '.join(mfr['hits'])}"
                if mfr["matched"]
                else (
                    "No OCR text extracted — mark for manual label verification"
                    if not raw_text
                    else f"OCR did not match expected manufacturer '{po.get('manufacturer')}'"
                )
            ),
            "medium" if raw_text else "low",
        ),
        _check(
            "serial_or_batch",
            bool(parsed.get("serial") or parsed.get("batch") or not raw_text),
            (
                f"serial={parsed.get('serial')} batch={parsed.get('batch')}"
                if (parsed.get("serial") or parsed.get("batch"))
                else ("OCR unavailable — manual serial capture required" if not raw_text else "No serial/batch found in OCR")
            ),
            "medium",
        ),
    ]

    # Manufacturer OCR fail only when text exists but doesn't match
    if not raw_text:
        checks[2]["result"] = "REVIEW"
        checks[2]["severity"] = "low"
    if not raw_text:
        checks[3]["result"] = "REVIEW"

    for key, label in (
        ("creepage_mm", "creepage"),
        ("height_mm", "height"),
        ("diameter_mm", "diameter"),
    ):
        spec = specs.get(key)
        value = measured.get(key)
        if not spec:
            continue
        if value is None:
            checks.append(
                _check(
                    f"dimension_{label}",
                    False,
                    f"{label} not provided by officer (nominal {spec['nominal']} ± {spec['tol']} mm)",
                    "medium",
                )
            )
            checks[-1]["result"] = "REVIEW"
            continue
        deviation = round(float(value) - float(spec["nominal"]), 3)
        ok = abs(deviation) <= float(spec["tol"])
        checks.append(
            _check(
                f"dimension_{label}",
                ok,
                f"{label} {value} mm vs {spec['nominal']} ± {spec['tol']} (dev {deviation:+})",
                "high",
            )
        )

    high_defects = [d for d in defects if float(d.get("confidence", 0)) >= 0.55]
    crack_or_chip = [d for d in high_defects if d.get("label") in {"crack", "chip"}]
    checks.append(
        _check(
            "surface_defects",
            len(crack_or_chip) == 0,
            (
                "No high-confidence crack/chip detections"
                if not crack_or_chip
                else f"{len(crack_or_chip)} defect(s): "
                + ", ".join(f"{d['label']}@{d['confidence']}" for d in crack_or_chip[:4])
            ),
            "critical",
        )
    )

    fails = [c for c in checks if c["result"] == "FAIL"]
    reviews = [c for c in checks if c["result"] == "REVIEW"]
    critical_fail = any(c["severity"] == "critical" and c["result"] == "FAIL" for c in checks)

    if critical_fail or any(c["check_name"] == "surface_defects" and c["result"] == "FAIL" for c in checks):
        decision = Decision.fail
    elif fails:
        # Dimension/manufacturer mismatches → review unless many hard fails
        hard = [c for c in fails if c["severity"] in {"high", "critical"}]
        decision = Decision.fail if len(hard) >= 2 else Decision.needs_review
    elif reviews:
        decision = Decision.needs_review
    else:
        decision = Decision.pass_

    narrative = _narrative(po, decision, checks, high_defects, parsed)

    return {
        "decision": decision,
        "checks": checks,
        "failed_checks": [c["check_name"] for c in fails],
        "review_checks": [c["check_name"] for c in reviews],
        "defect_count": len(high_defects),
        "narrative": narrative,
        "ocr_parsed": parsed,
        "manufacturer_match": mfr,
    }


def _manufacturer_ok(ocr_text: str, manufacturer: str, aliases: list[str]) -> dict[str, Any]:
    hay = (ocr_text or "").upper()
    hits = []
    for name in [manufacturer, *aliases]:
        token = (name or "").strip()
        if token and token.upper() in hay:
            hits.append(token)
    return {"matched": bool(hits), "hits": hits, "expected": manufacturer}


def _narrative(
    po: dict[str, Any],
    decision: Decision,
    checks: list[dict[str, Any]],
    defects: list[dict[str, Any]],
    parsed: dict[str, Any],
) -> str:
    status = {
        Decision.pass_: "PASS",
        Decision.fail: "FAIL",
        Decision.needs_review: "NEEDS MANUAL REVIEW",
        Decision.pending: "PENDING",
    }[decision]
    parts = [
        f"AI Material Inspector proposes {status} for PO {po.get('po_number')} "
        f"({po.get('material_name')}) from {po.get('manufacturer')}.",
    ]
    if defects:
        parts.append(
            "Visual pipeline flagged: "
            + ", ".join(f"{d.get('label')} ({d.get('confidence')})" for d in defects[:5])
            + "."
        )
    else:
        parts.append("No high-confidence surface crack/chip detections on uploaded images.")
    if parsed.get("serial") or parsed.get("batch"):
        parts.append(
            f"OCR extracted serial/batch markers: serial={parsed.get('serial')}, batch={parsed.get('batch')}."
        )
    failed = [c for c in checks if c["result"] != "PASS"]
    if failed:
        parts.append("Open items: " + "; ".join(f"{c['check_name']} ({c['result']})" for c in failed) + ".")
    parts.append("Final acceptance or rejection remains with the authorized store / quality officer.")
    return " ".join(parts)


def decision_label(decision: Decision) -> str:
    return {
        Decision.pass_: "PASS",
        Decision.fail: "FAIL",
        Decision.needs_review: "NEEDS_REVIEW",
        Decision.pending: "PENDING",
    }[decision]
