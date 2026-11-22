from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services import vision


def test_health():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_vision_detects_crack_like_lines(tmp_path: Path):
    img = np.full((400, 400, 3), 200, dtype=np.uint8)
    cv2.line(img, (80, 60), (300, 340), (30, 30, 30), 3)
    cv2.line(img, (120, 50), (280, 330), (20, 20, 20), 2)
    src = tmp_path / "crack.jpg"
    ann = tmp_path / "ann.jpg"
    cv2.imwrite(str(src), img)
    result = vision.analyze_image(src, ann)
    assert result["ok"]
    assert result["defect_count"] >= 1
    assert ann.exists()


def test_login_and_list_pos():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@tgspdcl.example", "password": "ChangeMeNow!23"},
        )
        assert res.status_code == 200
        token = res.json()["access_token"]
        pos = client.get("/api/v1/purchase-orders", headers={"Authorization": f"Bearer {token}"})
        assert pos.status_code == 200
        assert any(p["po_number"] == "4500123401" for p in pos.json())
