import base64
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

_SOURCE_PATTERN = r"^[a-z_]{1,32}$"


def _validate_b64_image(value: str) -> str:
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


class GeoPoint(StrictRequestModel):
    """Validated coordinates (previously an unvalidated dict interpolated into WKT; audit S13)."""
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)

    def wkt(self) -> str:
        return f"POINT({self.lng:.6f} {self.lat:.6f})"


class PrintedLabel(StrictRequestModel):
    """What the user reads off the printed pack, for QR-vs-label consistency checks."""
    mrp: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    batch_no: Optional[str] = Field(default=None, max_length=40)
    expiry_date: Optional[str] = Field(default=None, max_length=20)
    mfg_date: Optional[str] = Field(default=None, max_length=20)
    brand_name: Optional[str] = Field(default=None, max_length=120)
    generic_name: Optional[str] = Field(default=None, max_length=200)


class BarcodeVerifyRequest(StrictRequestModel):
    barcode: str = Field(..., min_length=1, max_length=512)
    location: Optional[GeoPoint] = None
    source: Optional[str] = Field(default="live", pattern=_SOURCE_PATTERN)
    # Client-claimed time (offline scans). Stored as client_reported_at; never the audit time.
    verified_at: Optional[str] = Field(default=None, max_length=40)
    printed: Optional[PrintedLabel] = None
    # Units in the pack (tablets/ml). Only used for the India ceiling-price comparison.
    units_in_pack: Optional[int] = Field(default=None, ge=1, le=10_000)


class ImageVerifyRequest(StrictRequestModel):
    image: str = Field(..., min_length=16)  # base64 encoded
    extracted_text: Optional[str] = Field(default=None, max_length=4000)
    location: Optional[GeoPoint] = None
    source: Optional[str] = Field(default="live", pattern=_SOURCE_PATTERN)
    verified_at: Optional[str] = Field(default=None, max_length=40)

    @field_validator("image")
    @classmethod
    def validate_image_payload(cls, value: str) -> str:
        return _validate_b64_image(value)


class InteractionCheckRequest(StrictRequestModel):
    drugs: list[str] = Field(..., min_length=2, max_length=10)


class InteractionsPhotoRequest(StrictRequestModel):
    image: str = Field(..., min_length=16)  # base64 encoded photo of multiple medicines

    @field_validator("image")
    @classmethod
    def validate_image_payload(cls, value: str) -> str:
        return _validate_b64_image(value)


class SymptomSafetyRequest(StrictRequestModel):
    symptoms: str = Field(..., min_length=2, max_length=1000)
    current_medications: list[str] = Field(default_factory=list, max_length=30)


class OfflineSyncRequest(StrictRequestModel):
    """A scan performed offline. The client's verdict is recorded as a *claim*, never trusted."""
    verification_id: Optional[str] = Field(default=None, max_length=64)
    brand_name: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=512)
    verdict: Optional[str] = Field(default=None, max_length=32)
    confidence: Optional[float] = Field(default=None, ge=0, le=100)
    verified_at: Optional[str] = Field(default=None, max_length=40)
    source: Optional[str] = Field(default="offline_cache", pattern=_SOURCE_PATTERN)


class BatchAuditRequest(StrictRequestModel):
    items: list[dict] = Field(..., min_length=1, max_length=500)


class PackCheckRequest(StrictRequestModel):
    qr_payload: Optional[str] = Field(default=None, max_length=2048)
    printed: Optional[PrintedLabel] = None
    units_in_pack: Optional[int] = Field(default=None, ge=1, le=10_000)


class PriceCheckRequest(StrictRequestModel):
    drug_name: str = Field(..., min_length=2, max_length=200)
    printed_mrp: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    units_in_pack: Optional[int] = Field(default=None, ge=1, le=10_000)
    dosage_form: Optional[str] = Field(default=None, max_length=40)
    strength: Optional[str] = Field(default=None, max_length=40)


class LasaCheckRequest(StrictRequestModel):
    name: str = Field(..., min_length=2, max_length=120)
    generic_name: Optional[str] = Field(default=None, max_length=200)


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
    # v2 additive fields (non-breaking). See docs/API_CHANGES.md.
    recall_status: str = "inconclusive"  # active | none_found | inconclusive
    verdict_reasons: list[str] = []
    audit_status: str = "recorded"  # recorded | failed
    pack_check: Optional[dict] = None
    batch_alerts: Optional[dict] = None
    lasa: Optional[dict] = None
    price_check: Optional[dict] = None
    name_match_approximate: bool = False
    safety_notice: str = (
        "A registry or barcode match shows a record exists; it does not prove this pack is genuine. "
        "If in doubt, do not use the medicine and consult a pharmacist."
    )


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
