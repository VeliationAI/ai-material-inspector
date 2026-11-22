from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class HealthOut(BaseModel):
    status: str
    version: str
    env: str
    database: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    email: str
    full_name: str
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    sap_code: str
    material_name: str
    material_category: str
    manufacturer: str
    manufacturer_aliases: list[str] = []
    quantity: int
    unit: str
    store: str
    standard: str
    voltage_kv: Optional[float] = None
    specs: dict[str, Any] = {}
    pilot_enabled: bool

    model_config = {"from_attributes": True}


class FindingOut(BaseModel):
    check_name: str
    result: str
    detail: str
    severity: str


class ImageOut(BaseModel):
    id: int
    angle: str
    path: str
    annotated_path: Optional[str] = None
    ocr_text: str = ""


class InspectionOut(BaseModel):
    id: int
    purchase_order_id: int
    po_number: str
    material_name: str
    ai_decision: str
    approval_status: str
    narrative: str
    summary: dict[str, Any] = {}
    measured_creepage_mm: Optional[float] = None
    measured_height_mm: Optional[float] = None
    measured_diameter_mm: Optional[float] = None
    findings: list[FindingOut] = []
    images: list[ImageOut] = []
    report_available: bool = False
    created_at: datetime


class ApprovalRequest(BaseModel):
    approve: bool = Field(description="True to approve AI decision path, False to reject receipt")
    notes: str = ""
