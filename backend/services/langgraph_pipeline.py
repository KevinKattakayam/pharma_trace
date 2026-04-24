"""
LangGraph Agent Pipeline for comprehensive drug verification.
Orchestrates multiple AI agents in a graph workflow:

1. Barcode Agent — validates barcode format, GTIN check
2. FDA Lookup Agent — queries OpenFDA for drug data
3. Recall Agent — checks active recalls and enforcement actions
4. Interaction Agent — cross-references drug interactions
5. Safety Agent — evaluates overall safety profile
6. Report Agent — generates final verification report

Uses Groq (Llama 3.3 70B) for fast inference at each node.
"""
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, Annotated
import operator


# ── Agent State ──

class DrugVerificationState(TypedDict):
    # Input
    barcode: str
    drug_names: list[str]
    patient_age: Optional[int]
    patient_weight: Optional[float]
    kidney_function: Optional[str]

    # Intermediate
    gtin_result: Optional[dict]
    fda_result: Optional[dict]
    drug_info: Optional[dict]
    recall_data: Optional[list]
    interactions: Optional[list]
    side_effects: Optional[list]
    cold_chain: Optional[dict]

    # Output
    verdict: Optional[str]
    confidence: Optional[float]
    evidence: Annotated[list, operator.add]
    report: Optional[dict]
    ai_summary: Optional[str]
    errors: Annotated[list, operator.add]


# ── Agent Nodes ──

async def barcode_agent(state: DrugVerificationState) -> dict:
    """Agent 1: Validate barcode format using WHO GTIN."""
    try:
        from services.gtin import validate_gtin
        barcode = state.get("barcode", "")
        if barcode:
            result = validate_gtin(barcode)
            return {
                "gtin_result": result,
                "evidence": [{"agent": "barcode", "check": "GTIN validation",
                              "status": "pass" if result.get("valid") else "warn",
                              "detail": f"{result.get('format', 'Unknown')} — {'valid' if result.get('check_digit_valid') else 'invalid'} check digit"}]
            }
    except Exception as e:
        return {"errors": [f"Barcode agent error: {str(e)}"]}
    return {"evidence": []}


async def fda_lookup_agent(state: DrugVerificationState) -> dict:
    """Agent 2: Query OpenFDA for drug information."""
    try:
        from services.openfda import lookup_by_ndc, extract_openfda_info, get_drug_label
        from config import get_settings
        settings = get_settings()

        barcode = state.get("barcode", "")
        ndc_to_lookup = barcode
        if state.get("gtin_result", {}).get("ndc_extracted"):
            ndc_to_lookup = state["gtin_result"]["ndc_extracted"]

        ndc_result = await lookup_by_ndc(ndc_to_lookup, api_key=settings.openfda_api_key)

        if ndc_result:
            info = extract_openfda_info(ndc_result)
            return {
                "fda_result": ndc_result,
                "drug_info": info,
                "evidence": [{"agent": "fda_lookup", "check": "OpenFDA database",
                              "status": "pass",
                              "detail": f"Found: {info.get('brand_name', 'Unknown')} ({info.get('generic_name', 'Unknown')}) by {info.get('manufacturer', 'Unknown')}"}]
            }
        else:
            return {
                "evidence": [{"agent": "fda_lookup", "check": "OpenFDA database",
                              "status": "fail",
                              "detail": "Drug NOT found in FDA National Drug Code database"}]
            }
    except Exception as e:
        return {"errors": [f"FDA lookup agent error: {str(e)}"]}


async def recall_agent(state: DrugVerificationState) -> dict:
    """Agent 3: Check for active recalls."""
    try:
        from services.openfda import check_recalls
        from config import get_settings
        settings = get_settings()

        drug_info = state.get("drug_info", {})
        recalls = await check_recalls(
            ndc=drug_info.get("ndc"),
            drug_name=drug_info.get("brand_name"),
            api_key=settings.openfda_api_key
        )

        status = "pass" if not recalls else "fail"
        detail = f"No active recalls" if not recalls else f"{len(recalls)} ACTIVE RECALL(S) found — {recalls[0].get('reason_for_recall', 'Unknown reason')[:100]}"

        return {
            "recall_data": recalls,
            "evidence": [{"agent": "recall", "check": "FDA recalls", "status": status, "detail": detail}]
        }
    except Exception as e:
        return {"errors": [f"Recall agent error: {str(e)}"]}


async def interaction_agent(state: DrugVerificationState) -> dict:
    """Agent 4: Check drug interactions if multiple drugs provided."""
    try:
        drug_names = state.get("drug_names", [])
        if len(drug_names) < 2:
            return {"evidence": []}

        from services.interactions import check_all_interactions
        result = await check_all_interactions(drug_names)

        interactions = result.get("interactions", [])
        if interactions:
            details = [f"{ix.drug_a} + {ix.drug_b}: {ix.severity.value}" for ix in interactions[:3]]
            return {
                "interactions": [ix.model_dump() for ix in interactions],
                "evidence": [{"agent": "interactions", "check": "Drug interactions",
                              "status": "fail" if result["overall_risk"].value == "high" else "warn",
                              "detail": f"{len(interactions)} interaction(s): {'; '.join(details)}"}]
            }
        return {
            "interactions": [],
            "evidence": [{"agent": "interactions", "check": "Drug interactions",
                          "status": "pass", "detail": "No interactions found between listed drugs"}]
        }
    except Exception as e:
        return {"errors": [f"Interaction agent error: {str(e)}"]}


async def safety_agent(state: DrugVerificationState) -> dict:
    """Agent 5: Compute overall safety verdict."""
    try:
        evidence = state.get("evidence", [])
        passes = sum(1 for e in evidence if e.get("status") == "pass")
        fails = sum(1 for e in evidence if e.get("status") == "fail")
        total = len(evidence) if evidence else 1

        if fails >= 2:
            verdict = "counterfeit"
            confidence = min(95.0, 50 + fails * 15)
        elif fails == 1:
            verdict = "suspicious"
            confidence = 60.0
        elif passes >= 3:
            verdict = "authentic"
            confidence = min(100.0, (passes / total) * 100)
        else:
            verdict = "unknown"
            confidence = 50.0

        return {"verdict": verdict, "confidence": round(confidence, 1)}
    except Exception as e:
        return {"verdict": "unknown", "confidence": 0.0, "errors": [f"Safety agent error: {str(e)}"]}


async def report_agent(state: DrugVerificationState) -> dict:
    """Agent 6: Generate final report with AI summary via Groq."""
    try:
        drug_info = state.get("drug_info", {})
        verdict = state.get("verdict", "unknown")
        confidence = state.get("confidence", 0.0)
        evidence = state.get("evidence", [])

        report = {
            "drug": drug_info.get("brand_name") or "Unknown",
            "generic": drug_info.get("generic_name") or "Unknown",
            "verdict": verdict,
            "confidence": confidence,
            "evidence_count": len(evidence),
            "evidence_summary": evidence
        }

        # Generate AI summary using Groq
        from services.groq_ai import _groq_chat
        evidence_text = "\n".join(f"- [{e.get('status')}] {e.get('detail', '')}" for e in evidence)
        ai_result = await _groq_chat([
            {
                "role": "system",
                "content": "You are a drug safety analyst. Write a brief 2-3 sentence summary of the verification result for the patient. Be clear and direct. Return JSON: {\"summary\": \"...\"}"
            },
            {
                "role": "user",
                "content": f"Drug: {report['drug']} ({report['generic']})\nVerdict: {verdict} ({confidence}% confidence)\nEvidence:\n{evidence_text}"
            }
        ], max_tokens=150)

        ai_summary = ai_result.get("summary", f"Verification complete: {verdict} ({confidence}% confidence)") if ai_result else f"Verification complete: {verdict} ({confidence}% confidence)"

        return {"report": report, "ai_summary": ai_summary}
    except Exception as e:
        return {"report": {"verdict": state.get("verdict", "unknown")}, "errors": [f"Report agent error: {str(e)}"]}


# ── Build the LangGraph ──

def build_verification_graph():
    """Build the 6-agent verification pipeline as a LangGraph StateGraph."""
    graph = StateGraph(DrugVerificationState)

    # Add nodes
    graph.add_node("barcode_agent", barcode_agent)
    graph.add_node("fda_lookup_agent", fda_lookup_agent)
    graph.add_node("recall_agent", recall_agent)
    graph.add_node("interaction_agent", interaction_agent)
    graph.add_node("safety_agent", safety_agent)
    graph.add_node("report_agent", report_agent)

    # Define edges (sequential pipeline)
    graph.set_entry_point("barcode_agent")
    graph.add_edge("barcode_agent", "fda_lookup_agent")
    graph.add_edge("fda_lookup_agent", "recall_agent")
    graph.add_edge("recall_agent", "interaction_agent")
    graph.add_edge("interaction_agent", "safety_agent")
    graph.add_edge("safety_agent", "report_agent")
    graph.add_edge("report_agent", END)

    return graph.compile()


# Compiled graph singleton
_compiled_graph = None


def get_verification_graph():
    """Get or create the compiled verification graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_verification_graph()
    return _compiled_graph


async def run_full_verification(barcode: str, drug_names: list[str] = None,
                                 patient_age: int = None, patient_weight: float = None,
                                 kidney_function: str = None) -> dict:
    """
    Run the complete 6-agent verification pipeline.
    Returns final report with verdict, confidence, evidence trail, and AI summary.
    """
    graph = get_verification_graph()

    initial_state = {
        "barcode": barcode,
        "drug_names": drug_names or [],
        "patient_age": patient_age,
        "patient_weight": patient_weight,
        "kidney_function": kidney_function,
        "evidence": [],
        "errors": []
    }

    result = await graph.ainvoke(initial_state)

    return {
        "verdict": result.get("verdict", "unknown"),
        "confidence": result.get("confidence", 0.0),
        "drug_info": result.get("drug_info"),
        "evidence": result.get("evidence", []),
        "interactions": result.get("interactions"),
        "recall_data": result.get("recall_data"),
        "report": result.get("report"),
        "ai_summary": result.get("ai_summary"),
        "errors": result.get("errors", []),
        "agents_executed": 6
    }
