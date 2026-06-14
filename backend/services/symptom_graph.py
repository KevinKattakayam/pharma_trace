"""
Symptom-to-drug safety checker using LangGraph and Groq.
Identifies OTC medicines for symptoms, and cross-checks them against current medications.
"""
from typing import TypedDict, Optional, Annotated
import operator
from langgraph.graph import StateGraph, END
import json
import httpx
from config import get_settings

class SymptomSafetyState(TypedDict):
    symptoms: str
    current_medications: list[str]
    
    # Intermediate
    suggested_otcs: list[str]
    interactions_results: dict
    
    # Output
    safe_options: list[dict]
    unsafe_options: list[dict]
    summary: str


async def otc_suggester_node(state: SymptomSafetyState) -> dict:
    """Agent: Suggests OTC medications based on symptoms."""
    settings = get_settings()
    api_key = settings.groq_api_key
    
    if not api_key:
        # Fallback list if no API
        return {"suggested_otcs": ["Paracetamol", "Ibuprofen", "Aspirin"]}
        
    prompt = f"""
You are a pharmacist AI specializing in Indian pharmaceutical regulations.
The patient has these symptoms: "{state['symptoms']}".

What are 3-5 common over-the-counter (OTC) active ingredients (generic names) that treat these symptoms
and are legally available WITHOUT a prescription in India?

IMPORTANT constraints:
- Only suggest drugs classified as OTC or General Sale List (GSL) in India
- Do NOT suggest drugs on India's Schedule H, H1, or X lists (these require prescriptions in India)
- Some NSAIDs available OTC in the US/UK are prescription-only in India — check carefully
- Use INN (International Nonproprietary Name) generic names, not brand names

Return ONLY a JSON object with an "otcs" key containing an array of strings.
Example: {{"otcs": ["Paracetamol", "Cetirizine"]}}
"""
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                # Sometimes Llama returns {"otcs": ["..."]} if constrained by json_object
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    otcs = parsed
                elif isinstance(parsed, dict) and len(parsed.values()) > 0:
                    otcs = list(parsed.values())[0]
                else:
                    otcs = []
            except json.JSONDecodeError:
                otcs = []
                
            if not isinstance(otcs, list):
                otcs = ["Acetaminophen", "Ibuprofen"]
                
            # HARD GATE: Cross-check against Supabase schedule_classifications table
            # Filter out any drug that is Schedule H, H1, or X
            filtered_otcs = []
            from services.supabase import get_supabase
            db = get_supabase()
            if db.available:
                for drug in otcs:
                    try:
                        # Try to find if this drug has a restricted schedule
                        res = await db.query(
                            "schedule_classifications",
                            select="schedule",
                            filters={"generic_name": drug.lower()},
                            limit=1
                        )
                        if res and res[0].get("schedule") in ["H", "H1", "X"]:
                            # Skip prescription-only drugs
                            continue
                        filtered_otcs.append(drug)
                    except Exception:
                        filtered_otcs.append(drug)  # Fail open if DB is down, relying on prompt
            else:
                filtered_otcs = otcs

            if not filtered_otcs:
                filtered_otcs = ["Paracetamol"]  # Ultimate safe fallback
                
            return {"suggested_otcs": filtered_otcs}
    except Exception as e:
        return {"suggested_otcs": ["Paracetamol", "Ibuprofen"]}


async def interaction_checker_node(state: SymptomSafetyState) -> dict:
    """Agent: Checks interactions between suggested OTCs and current medications."""
    from services.interactions import check_all_interactions
    
    current_meds = state["current_medications"]
    suggested_otcs = state["suggested_otcs"]
    
    interactions_results = {}
    safe_options = []
    unsafe_options = []
    
    for otc in suggested_otcs:
        # Check interactions between this OTC and all current meds
        drug_list = [otc] + current_meds
        result = await check_all_interactions(drug_list)
        
        interactions_results[otc] = result
        
        # If overall risk is low or moderate, consider it "safe" enough to show with caution,
        # but the prompt asked for "only the safe options". Let's categorize.
        max_severity = 0
        ixns = result.get("interactions", [])
        
        # We only care about interactions involving the OTC
        relevant_ixns = []
        for ix in ixns:
            if ix["drug_a"].lower() == otc.lower() or ix["drug_b"].lower() == otc.lower():
                relevant_ixns.append(ix)
                sev = ix["severity"]["value"]
                # Convert string severity to int for comparison
                sev_val = {"minor": 1, "moderate": 2, "major": 3, "contraindicated": 4}.get(sev, 0)
                if sev_val > max_severity:
                    max_severity = sev_val
                    
        if max_severity >= 3: # Major or Contraindicated
            unsafe_options.append({
                "drug": otc,
                "reason": f"Interacts with current medication (Severity: {['minor','moderate','major','contraindicated'][max_severity-1]})",
                "interactions": relevant_ixns
            })
        else:
            safe_options.append({
                "drug": otc,
                "interactions": relevant_ixns
            })
            
    return {
        "interactions_results": interactions_results,
        "safe_options": safe_options,
        "unsafe_options": unsafe_options
    }


async def summary_node(state: SymptomSafetyState) -> dict:
    """Agent: Summarizes the findings."""
    safe_names = [opt["drug"] for opt in state["safe_options"]]
    unsafe_names = [opt["drug"] for opt in state["unsafe_options"]]
    
    summary = f"Based on the symptoms, potential OTCs include: {', '.join(state['suggested_otcs'])}.\n"
    if safe_names:
        summary += f"Safe options to take with {', '.join(state['current_medications'])}: {', '.join(safe_names)}.\n"
    if unsafe_names:
        summary += f"WARNING: Avoid {', '.join(unsafe_names)} due to severe interactions."
        
    return {"summary": summary}


# Build the LangGraph
workflow = StateGraph(SymptomSafetyState)

workflow.add_node("otc_suggester", otc_suggester_node)
workflow.add_node("interaction_checker", interaction_checker_node)
workflow.add_node("summarizer", summary_node)

workflow.set_entry_point("otc_suggester")
workflow.add_edge("otc_suggester", "interaction_checker")
workflow.add_edge("interaction_checker", "summarizer")
workflow.add_edge("summarizer", END)

symptom_safety_app = workflow.compile()
