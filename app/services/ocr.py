"""OCR extraction for insulator labels / manufacturer markings."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_engine = None
_engine_error: str | None = None


def _get_engine():
    global _engine, _engine_error
    if _engine is not None or _engine_error:
        return _engine
    try:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
        logger.info("RapidOCR engine loaded")
    except Exception as exc:  # noqa: BLE001
        _engine_error = str(exc)
        logger.warning("RapidOCR unavailable: %s", exc)
        _engine = None
    return _engine


def extract_text(image_path: Path) -> dict[str, Any]:
    engine = _get_engine()
    lines: list[str] = []
    boxes: list[dict[str, Any]] = []

    if engine is not None:
        try:
            result, _ = engine(str(image_path))
            if result:
                for item in result:
                    # item: [box, text, score]
                    text = str(item[1]).strip()
                    score = float(item[2]) if len(item) > 2 else 0.0
                    if text:
                        lines.append(text)
                        boxes.append({"text": text, "score": round(score, 3)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR failed on %s: %s", image_path, exc)

    joined = "\n".join(lines)
    serial = _find_first(joined, [r"\b(?:SN|S/?N|SERIAL)[:\s#-]*([A-Z0-9-]{5,})\b", r"\b([A-Z]{2,}-\d{2,}-\d{3,})\b"])
    batch = _find_first(joined, [r"\b(?:BATCH|LOT)[:\s#-]*([A-Z0-9-]{4,})\b", r"\b(PI-\d{2}-\d{3,})\b"])
    model = _find_first(joined, [r"\b(?:MODEL|TYPE)[:\s#-]*([A-Z0-9-]{3,})\b", r"\b(\d{1,2}\s?kV)\b"])
    kv = _find_first(joined, [r"\b(11|33|66)\s?kV\b"])

    return {
        "engine": "rapidocr" if engine is not None else "unavailable",
        "raw_text": joined,
        "lines": lines,
        "boxes": boxes,
        "parsed": {
            "serial": serial,
            "batch": batch,
            "model": model,
            "voltage_marking": kv,
        },
        "error": _engine_error,
    }


def _find_first(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1) if m.lastindex else m.group(0)
    return None


def manufacturer_match(ocr_text: str, manufacturer: str, aliases: list[str]) -> dict[str, Any]:
    hay = (ocr_text or "").upper()
    candidates = [manufacturer] + list(aliases or [])
    hits = []
    for name in candidates:
        token = (name or "").strip()
        if not token:
            continue
        if token.upper() in hay:
            hits.append(token)
    return {
        "matched": bool(hits),
        "hits": hits,
        "expected": manufacturer,
    }
