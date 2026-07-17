from datetime import datetime
from typing import Optional
import base64
from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum


class StrictRequestModel(BaseModel):
    """Reject unexpected request fields instead of silently ignoring them."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CurrentUser(BaseModel):
    user_id: str
    role: str = "user"
    clinic_id: Optional[str] = None


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
    unknown = "unknown"
    low = "low"
    moderate = "moderate"
    high = "high"


# ── Request schemas ──

class BarcodeVerifyRequest(StrictRequestModel):
    barcode: str = Field(..., min_length=1, max_length=512)
    location: Optional[dict] = None
    source: Optional[str] = "live"
    verified_at: Optional[str] = None


class ImageVerifyRequest(StrictRequestModel):
    image: str = Field(..., min_length=16)  # base64 encoded
    extracted_text: Optional[str] = None
    location: Optional[dict] = None
    source: Optional[str] = "live"
    verified_at: Optional[str] = None

    @field_validator("image")
    @classmethod
    def validate_image_payload(cls, value: str) -> str:
        """Reject malformed or excessive image payloads before any AI/API call."""
        payload = value.split(",", 1)[-1] if value.startswith("data:") else value
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("image must be valid base64 data") from exc
        from config import get_settings
        if len(decoded) > get_settings().max_image_upload_bytes:
            raise ValueError("image exceeds the configured upload limit")
        return value


class InteractionCheckRequest(StrictRequestModel):
    drugs: list[str] = Field(..., min_length=2, max_length=10)


class InteractionsPhotoRequest(StrictRequestModel):
    image: str  # base64 encoded photo of multiple medicines


class SymptomSafetyRequest(StrictRequestModel):
    symptoms: str
    current_medications: list[str]


class DosageRequest(StrictRequestModel):
    age: int = Field(..., ge=0, le=120)
    weight_kg: float = Field(..., ge=1, le=300)
    kidney_function: Optional[str] = None  # "normal", "mild", "moderate", "severe"
    current_dose: Optional[str] = None


class ReportRequest(StrictRequestModel):
    drug_name: str
    barcode: Optional[str] = None
    description: str
    city: Optional[str] = None
    country: Optional[str] = None
    anonymous: bool = False
    photo_urls: Optional[list[str]] = None


class PharmacyReviewRequest(StrictRequestModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class CaregiverLinkRequest(StrictRequestModel):
    code: str


class BatchVerifyRequest(StrictRequestModel):
    barcodes: list[str] = Field(..., min_length=1, max_length=100)


class SafetyCaseCreateRequest(StrictRequestModel):
    verification_id: Optional[str] = None
    medicine_name: str = Field(..., min_length=2, max_length=160)
    batch_number: Optional[str] = Field(default=None, max_length=100)
    issue_type: str = Field(..., pattern="^(suspected_falsified|recall|quality_defect|storage_concern|adverse_event|other)$")
    notes: str = Field(..., min_length=10, max_length=2000)
    quarantined: bool = False


class SafetyCaseUpdateRequest(StrictRequestModel):
    status: str = Field(..., pattern="^(open|triaged|escalated|resolved|dismissed)$")
    resolution_note: Optional[str] = Field(default=None, max_length=2000)


class SafetyCaseResponse(BaseModel):
    id: str
    status: str
    medicine_name: str
    issue_type: str
    quarantined: bool
    created_at: str
    verification_id: Optional[str] = None
    resolution_note: Optional[str] = None


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
    identification_source: Optional[str] = None
    expiry_info: Optional[dict] = None
    shortage: Optional[dict] = None
    ai_generated: bool = False
    requires_human_review: bool = True
    verification_scope: str = "record_match_only"
    data_freshness: Optional[dict] = None


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
    ai_generated: bool = False
    clinical_review_required: bool = True
    data_source_status: str = "unvalidated_or_incomplete"


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
