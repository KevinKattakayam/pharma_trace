from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class VerificationMethod(str, Enum):
    barcode = "barcode"
    image = "image"
    manual = "manual"
    batch = "batch"


class Verdict(str, Enum):
    authentic = "authentic"
    suspicious = "suspicious"
    counterfeit = "counterfeit"
    unknown = "unknown"


class InteractionSeverity(str, Enum):
    none = "none"
    minor = "minor"
    moderate = "moderate"
    major = "major"
    contraindicated = "contraindicated"


class RiskLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"


# ── Request schemas ──

class BarcodeVerifyRequest(BaseModel):
    barcode: str
    location: Optional[dict] = None


class ImageVerifyRequest(BaseModel):
    image: str  # base64 encoded
    location: Optional[dict] = None


class InteractionCheckRequest(BaseModel):
    drugs: list[str] = Field(..., min_length=2, max_length=10)


class DosageRequest(BaseModel):
    age: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., ge=1, le=300)
    kidney_function: Optional[str] = None  # "normal", "mild", "moderate", "severe"
    current_dose: Optional[str] = None


class ReportRequest(BaseModel):
    drug_name: str
    barcode: Optional[str] = None
    description: str
    city: Optional[str] = None
    country: Optional[str] = None
    anonymous: bool = False
    photo_urls: Optional[list[str]] = None


class PharmacyReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class CaregiverLinkRequest(BaseModel):
    code: str


class BatchVerifyRequest(BaseModel):
    barcodes: list[str] = Field(..., min_length=1, max_length=100)


# ── Response schemas ──

class EvidenceItem(BaseModel):
    check: str
    status: str  # "pass", "fail", "warn"
    description: str
    weight: Optional[float] = None


class SideEffect(BaseModel):
    description: str
    severity: str  # "mild", "moderate", "severe"
    frequency: Optional[str] = None


class VerificationResponse(BaseModel):
    verification_id: str
    verdict: Verdict
    confidence: float
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None
    ndc: Optional[str] = None
    product_type: Optional[str] = None
    route: Optional[str] = None
    active_ingredients: Optional[str] = None
    has_recall: bool = False
    evidence: list[EvidenceItem] = []
    side_effects: list[SideEffect] = []
    audit_hash: Optional[str] = None


class DrugInteraction(BaseModel):
    drug_a: str
    drug_b: str
    severity: InteractionSeverity
    mechanism: Optional[str] = None
    clinical_effect: str
    recommendation: Optional[str] = None
    source: Optional[str] = None


class InteractionResponse(BaseModel):
    overall_risk: RiskLevel
    drug_count: int
    drug_names: list[str]
    interactions: list[DrugInteraction]
    matrix: list[list[str]]  # severity grid


class DosageAdvice(BaseModel):
    standard_dose: str
    recommended_dose: str
    risk_level: RiskLevel
    adjustments: list[str]
    warnings: list[str]


class GenericAlternative(BaseModel):
    name: str
    manufacturer: str
    ndc: str
    strength: Optional[str] = None
    route: Optional[str] = None


class ReportResponse(BaseModel):
    report_id: str
    anonymous_id: Optional[str] = None
    status: str = "pending"


class PharmacyResponse(BaseModel):
    name: str
    address: Optional[str] = None
    lat: float
    lng: float
    trust_score: float
    total_verifications: int = 0
    verification_pass_rate: Optional[float] = None
    flagged_reviews: int = 0


class AuditChainResponse(BaseModel):
    chain_valid: bool
    total_records: int
    last_hash: Optional[str] = None
    checked_at: str


class HeatmapReport(BaseModel):
    lat: float
    lng: float
    drug_name: Optional[str] = None
    city: Optional[str] = None
    status: str = "pending"
    created_at: Optional[str] = None
