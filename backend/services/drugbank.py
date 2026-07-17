"""
Drug interaction service using real-time APIs:
1. OpenFDA Label API — fetch drug_interactions section from official FDA labels (free, no key)
2. Groq AI (Llama 3.3) — parse raw FDA text into structured interaction data
3. OpenFDA Adverse Events — detect co-reported drug pairs from FAERS

No hardcoded/dummy data. Every interaction is fetched live from FDA databases.
"""
import httpx
import json
from typing import Optional
from config import get_settings

OPENFDA_BASE = "https://api.fda.gov"


async def fetch_fda_interactions(drug_name: str, api_key: str = "") -> Optional[str]:
    """Fetch the drug_interactions section from the FDA label for a drug."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            search = f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"'
            params = {"search": search, "limit": 1}
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/label.json", params=params)
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


async def parse_interactions_with_ai(drug_name: str, fda_text: str, other_drugs: list[str] = None) -> list[dict]:
    """
    Use Groq/Llama to parse raw FDA interaction text into structured data.
    If other_drugs are specified, specifically checks those pairs.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        return []

    other_drugs_context = ""
    if other_drugs:
        other_drugs_context = f"\n\nSpecifically check interactions with these drugs: {', '.join(other_drugs)}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
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
                            "content": """You are a pharmacist parsing FDA drug interaction data.
Extract specific drug-drug interactions from the FDA label text.
Return JSON array:
{
  "interactions": [
    {
      "interacting_drug": "drug name",
      "severity": "major|moderate|minor",
      "mechanism": "brief mechanism",
      "clinical_effect": "what happens to the patient",
      "recommendation": "what to do"
    }
  ]
}
Only include real interactions mentioned in the text. Do not invent any."""
                        },
                        {
                            "role": "user",
                            "content": f"Drug: {drug_name}\n\nFDA Label Drug Interactions section:\n{fda_text[:3000]}{other_drugs_context}"
                        }
                    ],
                    "max_tokens": 800,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                parsed = json.loads(content)
                return parsed.get("interactions", [])
    except Exception:
        pass
    return []


async def check_fda_adverse_cooccurrence(drug_a: str, drug_b: str, api_key: str = "") -> Optional[dict]:
    """
    Check if two drugs are frequently co-reported in FDA adverse event reports (FAERS).
    High co-reporting suggests a real-world interaction signal.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            search = (
                f'patient.drug.openfda.generic_name:"{drug_a.upper()}" AND '
                f'patient.drug.openfda.generic_name:"{drug_b.upper()}"'
            )
            params = {"search": search, "count": "patient.reaction.reactionmeddrapt.exact", "limit": 5}
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/event.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    total_reports = sum(r.get("count", 0) for r in results)
                    top_reactions = [r.get("term", "") for r in results[:5]]
                    return {
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "co_reported_count": total_reports,
                        "top_reactions": top_reactions,
                        "signal_strength": "strong" if total_reports > 100 else "moderate" if total_reports > 20 else "weak",
                        "source": "FDA FAERS"
                    }
        except Exception:
            pass
    return None


async def get_live_interactions(drug_names: list[str]) -> list[dict]:
    """
    Get all interactions between a list of drugs using live FDA APIs + Groq AI.
    Pipeline: OpenFDA Label → Groq parse → FAERS co-occurrence validation.
    """
    settings = get_settings()
    all_interactions = []
    seen_pairs = set()

    # For each drug, fetch its FDA label interactions section
    for drug in drug_names:
        fda_text = await fetch_fda_interactions(drug, api_key=settings.openfda_api_key)

        if fda_text and settings.groq_api_key:
            # Use AI to parse the raw FDA text and check against other drugs
            other_drugs = [d for d in drug_names if d.lower() != drug.lower()]
            parsed = await parse_interactions_with_ai(drug, fda_text, other_drugs)

            for ix in parsed:
                interacting = ix.get("interacting_drug", "").lower()
                # Only include if the interacting drug is in our list
                for other in drug_names:
                    if other.lower() != drug.lower() and (
                        other.lower() in interacting or interacting in other.lower()
                    ):
                        pair_key = tuple(sorted([drug.lower(), other.lower()]))
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            all_interactions.append({
                                "drug_a": drug,
                                "drug_b": other,
                                "severity": ix.get("severity", "moderate"),
                                "mechanism": ix.get("mechanism", ""),
                                "clinical_effect": ix.get("clinical_effect", ""),
                                "recommendation": ix.get("recommendation", ""),
                                "source": "FDA Label + AI Analysis"
                            })

    # Validate with FAERS co-occurrence data
    for ix in all_interactions:
        faers = await check_fda_adverse_cooccurrence(
            ix["drug_a"], ix["drug_b"], api_key=settings.openfda_api_key
        )
        if faers:
            ix["faers_signal"] = faers

    return all_interactions


async def lookup_rxcui(drug_name: str) -> Optional[str]:
    """Look up RxNorm CUI for a drug name (free NIH API, no key)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                params={"name": drug_name}
            )
            if resp.status_code == 200:
                data = resp.json()
                ids = data.get("idGroup", {}).get("rxnormId", [])
                if ids:
                    return ids[0]
        except Exception:
            pass
    return None
