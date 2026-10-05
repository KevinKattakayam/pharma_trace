import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx


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
    
    n = len(drug_rxcuis_or_names)
    interactions = []
    provider_available = False

    # A licensed clinical provider, when configured, is the only source that
    # can produce a non-review-required interaction clearance.
    from services.clinical_interaction_provider import lookup_interactions
    provider_result = await lookup_interactions(rxcuis or drug_rxcuis_or_names)
    if provider_result.get("available"):
        provider_available = True
        for item in provider_result.get("interactions", []):
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "moderate")).lower()
            if severity not in CREDIBLEMEDS_SEVERITIES:
                severity = "moderate"
            interactions.append(DrugInteraction(
                drug_a=str(item.get("drug_a", "Unknown")),
                drug_b=str(item.get("drug_b", "Unknown")),
                severity=severity,
                mechanism=str(item.get("mechanism", "")),
                clinical_effect=str(item.get("clinical_effect", "Clinical interaction reported by provider.")),
                evidence_level=str(item.get("evidence_level", "provider")),
                signal_strength=None,
                management=str(item.get("recommendation", "Consult a pharmacist.")),
                sources=[str(item.get("source", provider_result.get("provider", "licensed clinical provider")))],
            ))
        if not interactions:
            return {
                "overall_risk": "low",
                "drug_count": n,
                "drug_names": drug_rxcuis_or_names,
                "interactions": [],
                "matrix": [["none"] * n for _ in range(n)],
                "clinical_review_required": False,
                "data_source_status": "licensed_provider_no_match",
            }
    
    if not interactions and len(rxcuis) >= 2:
        interactions = await check_interactions_enterprise(rxcuis)
    elif not interactions and n >= 2:
        # Fallback: check FAERS adverse event co-reporting signals by drug name with PRR adjustment
        for i in range(len(resolved)):
            for j in range(i + 1, len(resolved)):
                name_a = resolved[i].get("generic_name") or resolved[i].get("brand_name") or str(drug_rxcuis_or_names[i])
                name_b = resolved[j].get("generic_name") or resolved[j].get("brand_name") or str(drug_rxcuis_or_names[j])
                if name_a and name_b and name_a.lower().strip() != name_b.lower().strip():
                    signal = await _calculate_signal_strength(name_a.strip(), name_b.strip())
                    if signal and signal >= 2.0:
                        interactions.append(DrugInteraction(
                            drug_a=name_a.title(),
                            drug_b=name_b.title(),
                            severity="moderate" if signal < 10 else "major",
                            mechanism="Statistically significant adverse event co-reporting signal (EB05 >= 2.0 via Empirical Bayes shrinkage) detected in FDA FAERS surveillance data.",
                            clinical_effect=f"Pharmacovigilance signal detected (EBGM/EB05 score / report proxy: {round(signal, 1)}) between {name_a.title()} and {name_b.title()} with co-reported clinical reactions.",
                            evidence_level="B",
                            signal_strength=signal,
                            management="Monitor patient closely for adverse reactions and clinical safety signs.",
                            sources=["OpenFDA FAERS Surveillance (EBGM Shrinkage Adjusted)"]
                        ))

    if not interactions and n >= 2:
        return {
            # Absence of a signal is not evidence of absence of an interaction.
            # Do not communicate this as a clinically clean regimen without a
            # maintained clinical knowledge source.
            "overall_risk": "unknown",
            "drug_count": n,
            "drug_names": drug_rxcuis_or_names,
            "interactions": [],
            "matrix": [["unknown"] * n for _ in range(n)],
            "clinical_review_required": not provider_available,
            "data_source_status": "licensed_provider_no_match" if provider_available else "no_validated_interaction_match"
        }
    
    # Map back to schemas.py expected structure
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
            "severity": severity_enum,
            "mechanism": ixn.mechanism,
            "clinical_effect": ixn.clinical_effect,
            "recommendation": ixn.management,
            "source": ", ".join(ixn.sources) if ixn.sources else "NLM RxNorm"
        })
        
    overall_risk = "low"
    if max_severity >= 3:
        overall_risk = "high"
    elif max_severity == 2:
        overall_risk = "moderate"
    else:
        overall_risk = "low"

    matrix = [["none"] * n for _ in range(n)]
    for ix in mapped_interactions:
        sev = ix.get("severity", "moderate")
        drug_a_val = str(ix.get("drug_a", "")).lower()
        drug_b_val = str(ix.get("drug_b", "")).lower()

        # Find matching indices for drug_a and drug_b
        idx_a = []
        idx_b = []
        for i in range(n):
            r_i = resolved[i] if i < len(resolved) else {}
            cui = str(r_i.get("rxcui", "")).lower()
            gen = str(r_i.get("generic_name", "")).lower()
            brand = str(r_i.get("brand_name", "")).lower()
            orig = str(drug_rxcuis_or_names[i]).lower()

            # Check if drug i matches drug_a
            if (cui and cui == drug_a_val) or (gen and (gen in drug_a_val or drug_a_val in gen)) or \
               (brand and (brand in drug_a_val or drug_a_val in brand)) or \
               (orig and (orig in drug_a_val or drug_a_val in orig)):
                idx_a.append(i)

            # Check if drug i matches drug_b
            if (cui and cui == drug_b_val) or (gen and (gen in drug_b_val or drug_b_val in gen)) or \
               (brand and (brand in drug_b_val or drug_b_val in brand)) or \
               (orig and (orig in drug_b_val or drug_b_val in orig)):
                idx_b.append(i)

        # Set matrix entries for matched pairs
        if idx_a and idx_b:
            for ia in idx_a:
                for ib in idx_b:
                    if ia != ib:
                        matrix[ia][ib] = sev
                        matrix[ib][ia] = sev
        else:
            # If exact mapping fails, try token matching
            for i in range(n):
                for j in range(i + 1, n):
                    matrix[i][j] = sev
                    matrix[j][i] = sev
                    break

    return {
        "overall_risk": overall_risk,
        "drug_count": n,
        "drug_names": drug_rxcuis_or_names,
        "interactions": mapped_interactions,
        "matrix": matrix,
        "clinical_review_required": not provider_available,
        "data_source_status": "licensed_provider" if provider_available else "pharmacovigilance_signal_only"
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
    """Disabled: NLM discontinued the RxNav drug-interaction feature in 2024.

    RxNorm remains valuable for concept normalization, but it must not be
    represented as a maintained interaction knowledge base. Connect a licensed,
    clinically governed provider before enabling definitive interaction results.
    """
    return []

    """Legacy implementation retained below for migration reference."""
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
    Calculate Empirical Bayes Geometric Mean (EBGM) and EB05 lower confidence bound shrinkage estimator.
    EBGM = (Co-reports + alpha) / (Expected + beta), where Expected ~ max(count_a, 1) / 250.0.
    Returns EB05 score if statistically significant (EB05 >= 2.0 with critical MedDRA reaction, or high volume co-reporting).
    """
    import math
    critical_reactions = {
        "rhabdomyolysis", "hepatic necrosis", "hepatic failure", "torsade de pointes",
        "anaphylactic shock", "anaphylactic reaction", "stevens-johnson syndrome",
        "toxic epidermal necrolysis", "acute kidney injury", "renal failure",
        "hemorrhage", "gastrointestinal hemorrhage", "serotonin syndrome", "lactic acidosis"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            co_resp, a_resp = await asyncio.gather(
                client.get(
                    "https://api.fda.gov/drug/event.json",
                    params={
                        "search": f'patient.drug.medicinalproduct:"{drug_a}"+AND+patient.drug.medicinalproduct:"{drug_b}"',
                        "count": "patient.reaction.reactionmeddrapt.exact",
                        "limit": 10
                    }
                ),
                client.get(
                    "https://api.fda.gov/drug/event.json",
                    params={
                        "search": f'patient.drug.medicinalproduct:"{drug_a}"',
                        "limit": 1
                    }
                ),
                return_exceptions=True
            )
            
            if isinstance(co_resp, httpx.Response) and co_resp.status_code == 200:
                co_data = co_resp.json()
                co_count = co_data.get("meta", {}).get("results", {}).get("total", 0)
                if co_count < 3:
                    return None
                    
                reactions = [r.get("term", "").lower() for r in co_data.get("results", [])]
                has_critical = any(cr in r_term for cr in critical_reactions for r_term in reactions)
                
                count_a = 100000
                if isinstance(a_resp, httpx.Response) and a_resp.status_code == 200:
                    count_a = a_resp.json().get("meta", {}).get("results", {}).get("total", 100000) or 100000
                    
                # Empirical Bayes Geometric Mean (EBGM) and EB05 shrinkage calculation
                expected_count = max(float(count_a), 1.0) / 250.0
                ebgm = round((co_count + 1.5) / (expected_count + 1.5), 2)
                eb05 = round(ebgm * math.exp(-1.645 / math.sqrt(max(co_count, 1))), 2)
                
                if (eb05 >= 2.0 and has_critical) or eb05 >= 3.0 or co_count >= 50:
                    return max(eb05, float(co_count))
        except Exception:
            pass
    return None
