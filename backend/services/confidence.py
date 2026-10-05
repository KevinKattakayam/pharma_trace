from typing import List, Optional, Tuple

from models.schemas import EvidenceItem


def bayesian_confidence(evidence_keys: list[str]) -> int:
    """Deprecated compatibility function.

    No labelled validation set exists for the former likelihood values, so this
    service no longer manufactures a probability of authenticity from rules.
    """
    return 0

# Negative-evidence codes that make a pack "suspicious" (ADR-0004). Each is a concrete,
# observable problem, unlike the former ``confidence < 50`` rule, which fired on every
# scan because confidence is always 0 without an authoritative serial check.
SUSPICION_CODES = {
    "serial_rejected": "Authorised serial-verification service rejected this pack.",
    "active_recall": "An active recall or regulator alert matches this product.",
    "batch_alert": "This batch number appears on a regulator quality alert.",
    "invalid_check_digit": "Barcode check digit is invalid (misprint or tampering).",
    "registry_miss": "Product was not found in any consulted registry.",
    "expired": "Pack is past its printed expiry date.",
    "label_inconsistent": "Label/QR data is internally inconsistent.",
    "vision_high_suspicion": "Image analysis flagged visible packaging anomalies.",
}


def assess_verdict(
    *,
    serial_verification: Optional[bool] = None,
    no_active_recall: Optional[bool] = None,
    registry_match: Optional[bool] = None,
    integrity_flags: Optional[List[str]] = None,
    confidence: float = 0.0,
) -> Tuple[str, List[str]]:
    """Return ``(verdict, reason_codes)``.

    * ``authentic`` and ``counterfeit`` are reserved for an authoritative serial response.
    * ``suspicious`` requires at least one concrete negative-evidence code.
    * Everything else is ``unknown``: a record match only, which still requires review.
    """
    reasons: List[str] = [f for f in (integrity_flags or []) if f in SUSPICION_CODES]
    if serial_verification is False:
        return "counterfeit", ["serial_rejected", *reasons]
    if no_active_recall is False:
        reasons.insert(0, "active_recall")
    if registry_match is False:
        reasons.append("registry_miss")
    if reasons:
        return "suspicious", list(dict.fromkeys(reasons))
    if serial_verification is True and no_active_recall is True and confidence >= 80:
        return "authentic", []
    return "unknown", []


def determine_verdict(
    confidence: float,
    *,
    serial_verification: Optional[bool] = None,
    no_active_recall: Optional[bool] = None,
    registry_match: Optional[bool] = None,
    integrity_flags: Optional[List[str]] = None,
) -> str:
    """Backward-compatible wrapper around :func:`assess_verdict`."""
    return assess_verdict(
        serial_verification=serial_verification,
        no_active_recall=no_active_recall,
        registry_match=registry_match,
        integrity_flags=integrity_flags,
        confidence=confidence,
    )[0]


def compute_confidence(
    barcode_valid: bool,
    openfda_match: bool,
    recall_status: bool,
    image_match: Optional[bool] = None,
    cold_chain_ok: Optional[bool] = None,
    report_history_clean: bool = True
) -> Tuple[float, List[EvidenceItem]]:
    evidence = []
    if barcode_valid:
        evidence.append(EvidenceItem(check="gtin_validation", status="pass", description="Barcode check digit is structurally valid; this is not an authenticity check.", weight=0.0))
    
    if openfda_match:
        evidence.append(EvidenceItem(
            check="openfda_match",
            status="pass",
            description="A matching record exists in a consulted registry (record match only, not proof the pack is genuine).",
            weight=0.0
        ))
    else:
        evidence.append(EvidenceItem(
            check="openfda_match",
            status="fail",
            description="No matching record found in the consulted registries.",
            weight=0.0
        ))
        
    if recall_status is True:
        evidence.append(EvidenceItem(
            check="recall_check",
            status="pass",
            description="No active recalls found",
            weight=0.0
        ))
    elif recall_status is False:
        evidence.append(EvidenceItem(
            check="recall_check",
            status="fail",
            description="ACTIVE RECALL DETECTED",
            weight=0.0
        ))
    else:
        evidence.append(EvidenceItem(check="recall_check", status="warn", description="Recall coverage is unavailable or incomplete.", weight=0.0))

    # Local weather is contextual information, not evidence of pack authenticity.
    if cold_chain_ok is True:
        evidence.append(EvidenceItem(
            check="cold_chain",
            status="pass",
            description="Local conditions are compatible with the labelled storage range; this does not verify product handling history.",
            weight=0.0
        ))
    elif cold_chain_ok is False:
        evidence.append(EvidenceItem(
            check="cold_chain",
            status="fail",
            description="Local conditions may exceed the labelled storage range; verify the product's actual handling history with the supplier.",
            weight=0.0
        ))
        
    # Only an authoritative serial response may populate authentication assurance.
    return 0.0, evidence
