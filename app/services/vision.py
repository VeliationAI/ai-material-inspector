"""OpenCV-based defect heuristics for porcelain insulator photos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_MAX_SIDE = 640


@dataclass
class DefectBox:
    label: str
    confidence: float
    x: int
    y: int
    w: int
    h: int


def _resize(raw: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = raw.shape[:2]
    scale = min(1.0, _MAX_SIDE / max(h, w))
    if scale < 1.0:
        raw = cv2.resize(raw, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return raw, scale


def _crack_candidates(gray: np.ndarray) -> list[DefectBox]:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[DefectBox] = []
    h, w = gray.shape[:2]
    min_area = max(60, int(0.0004 * h * w))
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / max(1, min(bw, bh))
        extent = area / max(1, bw * bh)
        if aspect >= 3.2 and extent < 0.45:
            conf = min(0.95, 0.45 + min(aspect, 12) / 20 + min(area, 5000) / 12000)
            boxes.append(DefectBox("crack", round(float(conf), 3), int(x), int(y), int(bw), int(bh)))
        elif aspect < 2.0 and 0.15 < extent < 0.7 and area > min_area * 2:
            conf = min(0.9, 0.4 + area / 8000)
            boxes.append(DefectBox("chip", round(float(conf), 3), int(x), int(y), int(bw), int(bh)))
    boxes.sort(key=lambda b: b.confidence, reverse=True)
    return boxes[:6]


def _surface_damage_score(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(lap.var())
    if variance > 420:
        return min(0.92, (variance - 420) / 800)
    return 0.0


def analyze_image(image_path: Path, annotated_path: Path) -> dict[str, Any]:
    raw = cv2.imread(str(image_path))
    if raw is None:
        return {
            "ok": False,
            "error": "unreadable_image",
            "defects": [],
            "defect_count": 0,
            "surface_damage_score": 0.0,
            "annotated_path": None,
        }

    raw, _ = _resize(raw)
    gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    defects = _crack_candidates(gray)
    surface = _surface_damage_score(gray)
    if surface >= 0.55 and not any(d.label == "surface_damage" for d in defects):
        h, w = gray.shape[:2]
        defects.append(
            DefectBox("surface_damage", round(surface, 3), int(w * 0.2), int(h * 0.2), int(w * 0.6), int(h * 0.6))
        )

    annotated = raw
    colors = {
        "crack": (40, 40, 220),
        "chip": (0, 140, 255),
        "surface_damage": (0, 200, 255),
    }
    for d in defects:
        color = colors.get(d.label, (0, 255, 0))
        cv2.rectangle(annotated, (d.x, d.y), (d.x + d.w, d.y + d.h), color, 2)
        cv2.putText(
            annotated,
            f"{d.label} {d.confidence:.2f}",
            (d.x, max(16, d.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    annotated_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(annotated_path), annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 72])

    return {
        "ok": True,
        "defects": [asdict(d) for d in defects],
        "defect_count": len(defects),
        "surface_damage_score": round(surface, 3),
        "annotated_path": str(annotated_path),
        "image_shape": list(raw.shape),
    }
