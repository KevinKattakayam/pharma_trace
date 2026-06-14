import math
from typing import Tuple, List, Optional
from models.schemas import EvidenceItem

PRIORS = {
    "base": 0.5,          # prior: 50% chance any scanned drug is legit
}

LIKELIHOODS = {
    "openfda_exact":    (0.98, 0.02),  # P(evidence|real), P(evidence|fake)
    "openfda_partial":  (0.75, 0.25),
    "no_recall":        (0.95, 0.40),
    "active_recall":    (0.02, 0.80),
    "ocr_matches_fda":  (0.90, 0.10),
    "cold_chain_ok":    (0.80, 0.50),
    "cold_chain_fail":  (0.10, 0.90),
    "rxnav_confirmed":  (0.85, 0.30),
    "gtin_valid":       (0.90, 0.20),
    "cdsco_match":      (0.88, 0.15),
    "drugbank_match":   (0.85, 0.20),
}

def bayesian_confidence(evidence_keys: list[str]) -> int:
    """
    Calculates the confidence score that a drug is legitimate using a Bayesian log-odds update.
    Returns an integer from 0 to 100.
    """
    log_odds = math.log(PRIORS["base"] / (1 - PRIORS["base"]))
    for key in evidence_keys:
        if key in LIKELIHOODS:
            p_real, p_fake = LIKELIHOODS[key]
            log_odds += math.log(p_real / p_fake)
    
    # Sigmoid function to convert log odds back to probability
    prob = 1 / (1 + math.exp(-log_odds))
    return round(prob * 100)

def determine_verdict(confidence: float) -> str:
    """Determine the final verdict string based on confidence score."""
    if confidence >= 80:
        return "authentic"
    elif confidence >= 50:
        return "suspicious"
    return "counterfeit"

def compute_confidence(
    barcode_valid: bool,
    openfda_match: bool,
    recall_status: bool,
    image_match: Optional[bool] = None,
    cold_chain_ok: Optional[bool] = None,
    report_history_clean: bool = True
) -> Tuple[float, List[EvidenceItem]]:
    evidence = []
    keys = []
    
    if barcode_valid:
        keys.append("gtin_valid")
    
    if openfda_match:
        keys.append("openfda_exact")
        evidence.append(EvidenceItem(
            check="openfda_match",
            status="pass",
            description="Verified against live OpenFDA database",
            weight=30.0
        ))
    else:
        evidence.append(EvidenceItem(
            check="openfda_match",
            status="fail",
            description="NDC not found in OpenFDA database",
            weight=30.0
        ))
        
    if recall_status:
        keys.append("no_recall")
        evidence.append(EvidenceItem(
            check="recall_check",
            status="pass",
            description="No active recalls found",
            weight=20.0
        ))
    else:
        keys.append("active_recall")
        evidence.append(EvidenceItem(
            check="recall_check",
            status="fail",
            description="ACTIVE RECALL DETECTED",
            weight=20.0
        ))

    # Cold chain penalty logic
    if cold_chain_ok is True:
        keys.append("cold_chain_ok")
        evidence.append(EvidenceItem(
            check="cold_chain",
            status="pass",
            description="Local weather meets storage requirements",
            weight=10.0
        ))
    elif cold_chain_ok is False:
        keys.append("cold_chain_fail")
        evidence.append(EvidenceItem(
            check="cold_chain",
            status="fail",
            description="WARNING: Local weather exceeds safe storage temperature",
            weight=10.0
        ))
        
    confidence_score = bayesian_confidence(keys)
    
    # Direct penalty if cold chain fails explicitly
    if cold_chain_ok is False:
        confidence_score = max(0, confidence_score - 15)
        
    return float(confidence_score), evidence
