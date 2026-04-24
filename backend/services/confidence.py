"""
Confidence scoring engine — aggregates evidence from all verification checks
into a weighted confidence score with transparent evidence trail.
"""
from models.schemas import EvidenceItem


def compute_confidence(
    barcode_valid: bool = False,
    openfda_match: bool = False,
    recall_status: bool = False,  # True = no recall
    image_match: bool | None = None,  # None = not analyzed
    cold_chain_ok: bool | None = None,
    report_history_clean: bool = True
) -> tuple[float, list[EvidenceItem]]:
    """
    Compute weighted confidence score with evidence trail.

    Weights:
    - Barcode validity: 20%
    - OpenFDA database match: 25%
    - Recall status (clean): 15%
    - Image/packaging analysis: 25%
    - Cold chain compliance: 10%
    - Report history: 5%
    """
    evidence = []
    total_weight = 0
    earned_weight = 0

    # Barcode validity (20%)
    weight = 20
    total_weight += weight
    if barcode_valid:
        earned_weight += weight
        evidence.append(EvidenceItem(
            check="barcode_validity",
            status="pass",
            description="Barcode format is valid and parseable",
            weight=weight
        ))
    else:
        evidence.append(EvidenceItem(
            check="barcode_validity",
            status="fail",
            description="Barcode could not be validated or is malformed",
            weight=weight
        ))

    # OpenFDA match (25%)
    weight = 25
    total_weight += weight
    if openfda_match:
        earned_weight += weight
        evidence.append(EvidenceItem(
            check="openfda_database",
            status="pass",
            description="Drug found in FDA National Drug Code database",
            weight=weight
        ))
    else:
        evidence.append(EvidenceItem(
            check="openfda_database",
            status="fail",
            description="Drug not found in FDA database — may be unregistered or counterfeit",
            weight=weight
        ))

    # Recall status (15%)
    weight = 15
    total_weight += weight
    if recall_status:
        earned_weight += weight
        evidence.append(EvidenceItem(
            check="recall_status",
            status="pass",
            description="No active recalls for this drug",
            weight=weight
        ))
    else:
        evidence.append(EvidenceItem(
            check="recall_status",
            status="fail",
            description="Active recall found — this drug has been recalled by the FDA",
            weight=weight
        ))

    # Image analysis (25%)
    weight = 25
    if image_match is not None:
        total_weight += weight
        if image_match:
            earned_weight += weight
            evidence.append(EvidenceItem(
                check="image_analysis",
                status="pass",
                description="Packaging and pill appearance match database reference images",
                weight=weight
            ))
        else:
            evidence.append(EvidenceItem(
                check="image_analysis",
                status="warn",
                description="Packaging appearance shows minor deviations from expected reference",
                weight=weight
            ))
            earned_weight += weight * 0.3  # Partial credit for inconclusive
    else:
        evidence.append(EvidenceItem(
            check="image_analysis",
            status="warn",
            description="No image provided — visual verification skipped",
            weight=weight
        ))
        # Don't add to total_weight since not analyzed

    # Cold chain (10%)
    weight = 10
    if cold_chain_ok is not None:
        total_weight += weight
        if cold_chain_ok:
            earned_weight += weight
            evidence.append(EvidenceItem(
                check="cold_chain",
                status="pass",
                description="Storage temperature conditions within acceptable range",
                weight=weight
            ))
        else:
            evidence.append(EvidenceItem(
                check="cold_chain",
                status="warn",
                description="Temperature conditions may have compromised drug integrity",
                weight=weight
            ))
    else:
        evidence.append(EvidenceItem(
            check="cold_chain",
            status="warn",
            description="Cold chain analysis not available for this location",
            weight=weight
        ))

    # Report history (5%)
    weight = 5
    total_weight += weight
    if report_history_clean:
        earned_weight += weight
        evidence.append(EvidenceItem(
            check="report_history",
            status="pass",
            description="No suspicious reports linked to this drug or batch",
            weight=weight
        ))
    else:
        evidence.append(EvidenceItem(
            check="report_history",
            status="fail",
            description="Previous suspicious reports found for this drug or manufacturer",
            weight=weight
        ))

    # Compute percentage
    confidence = (earned_weight / max(total_weight, 1)) * 100

    return round(confidence, 1), evidence


def determine_verdict(confidence: float) -> str:
    """Determine verdict based on confidence score."""
    if confidence >= 80:
        return "authentic"
    elif confidence >= 50:
        return "suspicious"
    elif confidence >= 20:
        return "counterfeit"
    else:
        return "unknown"
