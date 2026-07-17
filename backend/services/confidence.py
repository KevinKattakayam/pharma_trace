from typing import Tuple, List, Optional
from models.schemas import EvidenceItem

def bayesian_confidence(evidence_keys: list[str]) -> int:
    """Deprecated compatibility function.

    No labelled validation set exists for the former likelihood values, so this
    service no longer manufactures a probability of authenticity from rules.
    """
    return 0

def determine_verdict(
    confidence: float,
    *,
    serial_verification: Optional[bool] = None,
    no_active_recall: Optional[bool] = None,
) -> str:
    """Return a safety-first result, not an unvalidated probability claim.

    Registry and barcode matches establish that a *record* may exist; they cannot
    establish that a physical pack is genuine. ``authentic`` and ``counterfeit``
    are therefore reserved for an authoritative manufacturer/distributor serial
    response. All other cases require review when a decision matters.
    """
    if serial_verification is True and no_active_recall is True and confidence >= 80:
        return "authentic"
    if serial_verification is False:
        return "counterfeit"
    if no_active_recall is False or confidence < 50:
        return "suspicious"
    return "unknown"

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
            description="Verified against live OpenFDA database",
            weight=0.0
        ))
    else:
        evidence.append(EvidenceItem(
            check="openfda_match",
            status="fail",
            description="NDC not found in OpenFDA database",
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
