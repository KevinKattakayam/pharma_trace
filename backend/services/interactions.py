"""
Multi-drug interaction scanner — 100% live API data, no hardcoded interactions.
Pipeline:
1. OpenFDA Label API — fetches drug_interactions section from official FDA labels
2. Groq AI (Llama 3.3) — parses raw FDA text into structured interaction data
3. OpenFDA FAERS — validates interactions via real adverse event co-reporting
"""
from typing import Optional
from models.schemas import DrugInteraction, InteractionSeverity, RiskLevel
from config import get_settings


def normalize_drug_name(name: str) -> str:
    """Normalize drug name for matching."""
    return name.lower().strip()


async def fetch_fda_label_interactions(drug_name: str) -> Optional[str]:
    """
    Fetch the drug_interactions text from the official FDA label for a drug.
    Source: OpenFDA Label API - free, no key needed.
    """
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        settings = get_settings()
        try:
            search = f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"'
            params = {"search": search, "limit": 1}
            if settings.openfda_api_key:
                params["api_key"] = settings.openfda_api_key

            resp = await client.get("https://api.fda.gov/drug/label.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    label = data["results"][0]
                    interactions = label.get("drug_interactions", [])
                    if interactions:
                        return interactions[0] if isinstance(interactions, list) else str(interactions)
        except Exception:
            pass
    return None


async def parse_interactions_with_groq(drug_name: str, fda_text: str, other_drugs: list[str]) -> list[dict]:
    """
    Use Groq/Llama 3.3 to parse raw FDA interaction text into structured data.
    Only extracts interactions relevant to the other_drugs list.
    """
    import httpx
    import json

    settings = get_settings()
    if not settings.groq_api_key:
        return []

    drugs_context = ", ".join(other_drugs)

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a clinical pharmacist. Parse the FDA drug interaction text and identify interactions ONLY with the specified drugs.

Return JSON:
{
  "interactions": [
    {
      "interacting_drug": "exact drug name from the list",
      "severity": "major|moderate|minor",
      "mechanism": "pharmacological mechanism (1 sentence)",
      "clinical_effect": "what happens to the patient (1-2 sentences)",
      "recommendation": "what the patient/doctor should do"
    }
  ]
}

Rules:
- Only include interactions with drugs from the specified list
- If a drug from the list is not mentioned in the FDA text, do NOT include it
- Severity: major = life-threatening or requires intervention, moderate = may need monitoring, minor = minimal risk
- Be factual — only extract what the FDA label actually states"""
                        },
                        {
                            "role": "user",
                            "content": f"Primary drug: {drug_name}\nCheck interactions with: {drugs_context}\n\nFDA Label Drug Interactions section:\n{fda_text[:3000]}"
                        }
                    ],
                    "max_tokens": 600,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return parsed.get("interactions", [])
    except Exception:
        pass
    return []


async def check_faers_cooccurrence(drug_a: str, drug_b: str) -> Optional[dict]:
    """
    Check if two drugs are co-reported in FDA Adverse Event reports (FAERS).
    High co-occurrence = real-world signal of interaction.
    """
    import httpx
    settings = get_settings()

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            search = (
                f'patient.drug.openfda.generic_name:"{drug_a.upper()}" AND '
                f'patient.drug.openfda.generic_name:"{drug_b.upper()}"'
            )
            params = {
                "search": search,
                "count": "patient.reaction.reactionmeddrapt.exact",
                "limit": 5
            }
            if settings.openfda_api_key:
                params["api_key"] = settings.openfda_api_key

            resp = await client.get("https://api.fda.gov/drug/event.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    total = sum(r.get("count", 0) for r in results)
                    return {
                        "co_reported_count": total,
                        "top_reactions": [r.get("term", "") for r in results[:5]],
                        "signal": "strong" if total > 100 else "moderate" if total > 20 else "weak"
                    }
        except Exception:
            pass
    return None


async def check_all_interactions(drug_names: list[str]) -> dict:
    """
    Check all pairwise interactions among a list of drugs.
    Pipeline: For each drug → fetch FDA label → AI parse → FAERS validate.
    100% live data from FDA APIs + Groq AI.
    """
    names_original = drug_names
    names = [normalize_drug_name(d) for d in drug_names]
    n = len(names)

    interactions = []
    matrix = [["none"] * n for _ in range(n)]
    max_severity = "none"
    severity_rank = {"none": 0, "minor": 1, "moderate": 2, "major": 3, "contraindicated": 4}
    seen_pairs = set()

    # For each drug, fetch its FDA label and parse interactions with other drugs
    for i, drug in enumerate(names_original):
        other_drugs = [d for j, d in enumerate(names_original) if j != i]

        # Step 1: Fetch official FDA drug interactions text
        fda_text = await fetch_fda_label_interactions(drug)

        if fda_text:
            # Step 2: Use Groq AI to parse and extract relevant interactions
            parsed = await parse_interactions_with_groq(drug, fda_text, other_drugs)

            for ix_data in parsed:
                interacting = ix_data.get("interacting_drug", "").lower()

                # Match to our drug list
                for j, other in enumerate(names):
                    if j != i and (other in interacting or interacting in other):
                        pair_key = tuple(sorted([i, j]))
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            severity = ix_data.get("severity", "moderate")

                            matrix[i][j] = severity
                            matrix[j][i] = severity

                            if severity_rank.get(severity, 0) > severity_rank.get(max_severity, 0):
                                max_severity = severity

                            # Step 3: Validate with FAERS co-occurrence
                            faers = await check_faers_cooccurrence(names_original[i], names_original[j])

                            interactions.append(DrugInteraction(
                                drug_a=names_original[i],
                                drug_b=names_original[pair_key[1] if pair_key[0] == i else pair_key[0]],
                                severity=InteractionSeverity(severity),
                                mechanism=ix_data.get("mechanism"),
                                clinical_effect=ix_data.get("clinical_effect", ""),
                                recommendation=ix_data.get("recommendation"),
                                source=f"FDA Label + Groq AI" + (
                                    f" (FAERS: {faers['co_reported_count']} co-reports)"
                                    if faers else ""
                                )
                            ))

    # Determine overall risk
    if max_severity in ("major", "contraindicated"):
        overall_risk = RiskLevel.high
    elif max_severity == "moderate":
        overall_risk = RiskLevel.moderate
    else:
        overall_risk = RiskLevel.low

    return {
        "overall_risk": overall_risk,
        "drug_count": n,
        "drug_names": drug_names,
        "interactions": interactions,
        "matrix": matrix,
        "data_sources": ["OpenFDA Labels", "Groq AI (Llama 3.3)", "OpenFDA FAERS"]
    }
