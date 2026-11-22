"""PDF inspection report generation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fpdf import FPDF


def _ascii(text: Any) -> str:
    raw = str(text or "")
    raw = raw.replace("—", "-").replace("–", "-").replace("±", "+/-").replace("·", "-")
    return re.sub(r"[^\x20-\x7E\n]", "?", raw)


class ReportPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, "AI Material Inspector - Inspection Report", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "TGSPDCL Stores / Challenge 11 demo / Synthetic PO data", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")


def build_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    decision = _ascii(payload.get("decision_label", "PENDING"))
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, decision, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _ascii(payload.get("narrative", "")))
    pdf.ln(3)

    po = payload.get("purchase_order") or {}
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Purchase order", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in (
        ("PO Number", po.get("po_number")),
        ("SAP Code", po.get("sap_code")),
        ("Material", po.get("material_name")),
        ("Manufacturer", po.get("manufacturer")),
        ("Store", po.get("store")),
        ("Standard", po.get("standard")),
        ("Quantity", str(po.get("quantity"))),
    ):
        pdf.cell(45, 6, f"{label}:", border=0)
        pdf.cell(0, 6, _ascii(value or "-"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Checks", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(45, 6, "Check", border=1)
    pdf.cell(25, 6, "Result", border=1)
    pdf.cell(0, 6, "Detail", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    for check in payload.get("checks") or []:
        detail = _ascii(check.get("detail", ""))[:90]
        pdf.cell(45, 6, _ascii(check.get("check_name", ""))[:28], border=1)
        pdf.cell(25, 6, _ascii(check.get("result", "")), border=1)
        pdf.cell(0, 6, detail, border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Measurements (officer entered)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    measured = payload.get("measured") or {}
    for key, label in (
        ("creepage_mm", "Creepage mm"),
        ("height_mm", "Height mm"),
        ("diameter_mm", "Diameter mm"),
    ):
        val = measured.get(key)
        pdf.cell(0, 6, f"{label}: {val if val is not None else '-'}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0,
        5,
        "Human approval required before SAP goods receipt. "
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        "Illustrative demo - not actual utility acceptance criteria.",
    )

    images = payload.get("annotated_images") or []
    for img in images[:3]:
        p = Path(img)
        if p.exists():
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, f"Evidence: {_ascii(p.name)}", new_x="LMARGIN", new_y="NEXT")
            try:
                pdf.image(str(p), w=180)
            except Exception:  # noqa: BLE001
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 6, "(image could not be embedded)", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(path))
    return path
