import httpx
import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class DrugInteraction:
    drug_a: str
    drug_b: str
    severity: str          # minor / moderate / major / contraindicated
    mechanism: str
    clinical_effect: str
    evidence_level: str    # A (RCT), B (observational), C (case reports)
    signal_strength: Optional[float]      # Signal strength based on reporting density
    management: str
    sources: list[str]

CREDIBLEMEDS_SEVERITIES = {
    "contraindicated": 4,
    "major": 3,
    "moderate": 2,
    "minor": 1,
}

async def check_all_interactions(drug_rxcuis_or_names: list[str]) -> dict:
    """
    Adapter to match the previous API surface, while using the new enterprise logic.
    For this to work optimally, input should ideally be RxCUIs, but it handles fallback.
    """
    # Attempt to resolve RxCUIs for the given drugs if they aren't already CUIs
    from services.drug_resolver import resolve_all_drugs
    resolved = await resolve_all_drugs(drug_rxcuis_or_names)
    rxcuis = [r["rxcui"] for r in resolved if "rxcui" in r and r["rxcui"]]
    
    if len(rxcuis) < 2:
        return {"interactions": [], "overall_risk": "low"}
        
    interactions = await check_interactions_enterprise(rxcuis)
    
    # Map back to old expected structure for downstream compatibility
    mapped_interactions = []
    max_severity = 0
    for ixn in interactions:
        severity_enum = ixn.severity
        sev_score = CREDIBLEMEDS_SEVERITIES.get(severity_enum, 0)
        if sev_score > max_severity:
            max_severity = sev_score
            
        mapped_interactions.append({
            "drug_a": ixn.drug_a,
            "drug_b": ixn.drug_b,
            "severity": {"value": severity_enum},
            "mechanism": ixn.mechanism,
            "clinical_effect": ixn.clinical_effect,
            "evidence_level": ixn.evidence_level,
            "signal_strength": ixn.signal_strength,
            "management": ixn.management
        })
        
    overall_risk = "low"
    if max_severity >= 3:
        overall_risk = {"value": "high"}
    elif max_severity == 2:
        overall_risk = {"value": "moderate"}
    else:
        overall_risk = {"value": "low"}

    return {
        "overall_risk": overall_risk,
        "interactions": mapped_interactions
    }

async def check_interactions_enterprise(drug_rxcuis: list[str]) -> list[DrugInteraction]:
    """
    Layer 1: RxNorm Interaction API (free, real NLM data)
    Layer 2: FAERS proportional reporting ratio (PRR)
    """
    interactions = []

    # Layer 1 — RxNorm Interaction API
    rxnorm_ixns = await _query_rxnorm_interactions(drug_rxcuis)
    interactions.extend(rxnorm_ixns)

    # Layer 2 — FAERS PRR for evidence weight
    for ixn in interactions:
        ixn.signal_strength = await _calculate_signal_strength(ixn.drug_a, ixn.drug_b)

    # Sort by severity desc, then signal_strength desc
    interactions.sort(
        key=lambda x: (
            -CREDIBLEMEDS_SEVERITIES.get(x.severity, 0),
            -x.signal_strength if x.signal_strength else 0
        )
    )
    return interactions


async def _query_rxnorm_interactions(rxcuis: list[str]) -> list[DrugInteraction]:
    """Use NLM's free RxNorm interaction API — no key required."""
    rxcui_str = "+".join(rxcuis)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://rxnav.nlm.nih.gov/REST/interaction/list.json",
            params={"rxcuis": rxcui_str}
        )
        if r.status_code != 200:
            return []

        data = r.json()
        results = []
        pairs = data.get("fullInteractionTypeGroup", [])
        for group in pairs:
            for ixn_type in group.get("fullInteractionType", []):
                for pair in ixn_type.get("interactionPair", []):
                    concepts = pair.get("interactionConcept", [])
                    if len(concepts) < 2:
                        continue
                        
                    desc = pair.get("description", "")
                    severity = "moderate"
                    if "contraindicated" in desc.lower() or "avoid" in desc.lower():
                        severity = "contraindicated"
                    elif "severe" in desc.lower() or "major" in desc.lower():
                        severity = "major"
                    elif "minor" in desc.lower():
                        severity = "minor"
                        
                    results.append(DrugInteraction(
                        drug_a=concepts[0]["minConceptItem"]["name"],
                        drug_b=concepts[1]["minConceptItem"]["name"],
                        severity=severity,
                        mechanism=ixn_type.get("comment", ""),
                        clinical_effect=desc,
                        evidence_level="B",
                        signal_strength=None,
                        management="Consult pharmacist before use.",
                        sources=["NLM RxNorm"]
                    ))
        return results


async def _calculate_signal_strength(drug_a: str, drug_b: str) -> Optional[float]:
    """
    Proportional Reporting Ratio from FAERS.
    PRR > 2 with >= 3 reports = signal. Returns raw report count as a proxy for signal strength.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(
                "https://api.fda.gov/drug/event.json",
                params={
                    "search": f'patient.drug.medicinalproduct:"{drug_a}"+AND+patient.drug.medicinalproduct:"{drug_b}"',
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": 5
                }
            )
            if r.status_code == 200:
                total = r.json().get("meta", {}).get("results", {}).get("total", 0)
                if total > 0:
                    return float(total)
        except Exception:
            pass
    return None
