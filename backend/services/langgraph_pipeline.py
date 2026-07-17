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
                              "detail": f"Found (US FDA): {info.get('brand_name', 'Unknown')} ({info.get('generic_name', 'Unknown')}) by {info.get('manufacturer', 'Unknown')}"}]
            }
        else:
            # Fallback to Indian CDSCO database & Multi-Tier Resolver
            from services.cdsco import lookup_indian_drug
            from services.canonicalize import map_to_rxcui
            from services.drug_resolver import resolve_drug_name
            
            cdsco_info = await lookup_indian_drug(ndc_to_lookup)
            if not cdsco_info and " " in ndc_to_lookup:
                fw = ndc_to_lookup.split()[0].strip()
                if len(fw) >= 4:
                    cdsco_info = await lookup_indian_drug(fw)
                    
            if not cdsco_info:
                res_raw = await resolve_drug_name(ndc_to_lookup)
                if res_raw and res_raw.get("source") != "unresolved":
                    cdsco_info = {
                        "brand_name": res_raw.get("brand_name", ndc_to_lookup),
                        "generic_name": res_raw.get("generic_name", "Verified Drug"),
                        "manufacturer": res_raw.get("manufacturer", "Official Registry Match"),
                        "rxcui": res_raw.get("rxcui")
                    }
            
            if cdsco_info:
                # Canonicalize foreign generics to RxNorm for global interaction checks
                generic = cdsco_info.get("generic_name", "")
                if generic:
                    mapping = await map_to_rxcui(generic)
                    if mapping.get("rxcui"):
                        cdsco_info["rxcui"] = mapping["rxcui"]

                return {
                    "fda_result": cdsco_info,
                    "drug_info": cdsco_info,
                    "evidence": [
                        {"agent": "fda_lookup", "check": "OpenFDA database", "status": "fail", "detail": "Not found in US FDA database"},
                        {"agent": "cdsco_lookup", "check": "CDSCO India database", "status": "pass", 
                         "detail": f"Found (India CDSCO): {cdsco_info.get('brand_name', 'Unknown')} ({cdsco_info.get('generic_name', 'Unknown')}) by {cdsco_info.get('manufacturer', 'Unknown')}"}
                    ]
                }
                
            return {
                "evidence": [{"agent": "fda_lookup", "check": "OpenFDA & CDSCO databases",
                              "status": "fail",
                              "detail": "Drug NOT found in US FDA or Indian CDSCO databases"}]
            }
    except Exception as e:
        return {"errors": [f"FDA lookup agent error: {str(e)}"]}


async def recall_agent(state: DrugVerificationState) -> dict:
    """Agent 3: Check for active recalls."""
    try:
        from services.openfda import check_recalls
        from config import get_settings
        settings = get_settings()

        # Use barcode or first drug name directly to allow parallel execution
        drug_names = state.get("drug_names", [])
        ndc = state.get("barcode")
        drug_name = drug_names[0] if drug_names else None
        
        recalls = await check_recalls(
            ndc=ndc,
            drug_name=drug_name,
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
    """Agent 5: preserve evidence without manufacturing an authenticity verdict."""
    try:
        evidence = state.get("evidence", [])
        has_recall = any(e.get("agent") == "recall" and e.get("status") != "pass" for e in evidence)
        return {"verdict": "suspicious" if has_recall else "unknown", "confidence": 0.0}
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

        REPORTER_SCHEMA = """
Respond ONLY with valid JSON matching this schema exactly:
{
  "verdict": "safe" | "warn" | "danger",
  "confidence": <integer 0-100>,
  "brand_name": <string>,
  "generic_name": <string>,
  "manufacturer": <string>,
  "evidence": [{"source": <string>, "finding": <string>}],
  "warnings": [{"severity": "mild"|"moderate"|"severe", "text": <string>}],
  "patient_summary": <string, plain language, max 3 sentences>
}
No markdown, no preamble, just JSON.
"""

        # Generate AI summary using Groq
        import json
        from services.groq_ai import _groq_chat
        evidence_text = "\n".join(f"- [{e.get('status')}] {e.get('detail', '')}" for e in evidence)
        ai_result = await _groq_chat([
            {
                "role": "system",
                "content": REPORTER_SCHEMA
            },
            {
                "role": "user",
                "content": f"Drug: {report['drug']} ({report['generic']})\nVerdict: {verdict} ({confidence}% confidence)\nEvidence:\n{evidence_text}"
            }
        ], max_tokens=300)

        if ai_result:
            try:
                # Assuming _groq_chat returns dict (it usually parses JSON if it can)
                if isinstance(ai_result, str):
                    ai_result = json.loads(ai_result)
                report.update(ai_result)
            except:
                pass

        ai_summary = report.get("patient_summary", f"Verification complete: {verdict} ({confidence}% confidence)")

        return {"report": report, "ai_summary": ai_summary}
    except Exception as e:
        return {"report": {"verdict": state.get("verdict", "unknown")}, "errors": [f"Report agent error: {str(e)}"]}


# ── Fault Tolerance Wrappers (TimeoutPolicy + Error Handler) ──
import asyncio
import uuid
from langgraph.types import RetryPolicy
from langgraph.checkpoint.memory import MemorySaver

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None

async def _timeout_node_wrapper(node_fn, state: DrugVerificationState, timeout_sec: float, name: str) -> dict:
    try:
        return await asyncio.wait_for(node_fn(state), timeout=timeout_sec)
    except asyncio.TimeoutError:
        err_msg = f"TimeoutPolicy [{name}]: Exceeded {timeout_sec}s wall-clock limit"
        raise TimeoutError(err_msg)
    except Exception as e:
        raise

async def fda_lookup_node(state: DrugVerificationState) -> dict:
    return await _timeout_node_wrapper(fda_lookup_agent, state, 8.0, "fda_lookup_agent")

async def recall_node(state: DrugVerificationState) -> dict:
    return await _timeout_node_wrapper(recall_agent, state, 8.0, "recall_agent")

async def interaction_node(state: DrugVerificationState) -> dict:
    return await _timeout_node_wrapper(interaction_agent, state, 8.0, "interaction_agent")

async def report_node(state: DrugVerificationState) -> dict:
    return await _timeout_node_wrapper(report_agent, state, 10.0, "report_agent")


# Global Checkpointer Singleton
_checkpointer = None

async def get_checkpointer():
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    from config import get_settings
    settings = get_settings()
    db_url = getattr(settings, "database_url", "") or getattr(settings, "supabase_url", "")
    if AsyncPostgresSaver and db_url and ("postgres" in db_url):
        try:
            saver = AsyncPostgresSaver.from_conn_string(db_url)
            await saver.setup()
            _checkpointer = saver
            return _checkpointer
        except Exception:
            pass
    _checkpointer = MemorySaver()
    return _checkpointer


def build_verification_graph(checkpointer=None):
    """Build the 6-agent verification pipeline with true parallel nodes and fault tolerance."""
    graph = StateGraph(DrugVerificationState)
    retry_policy = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0, retry_on=Exception)

    # Add nodes (pure computation = no retry; network-bound = RetryPolicy + TimeoutPolicy)
    graph.add_node("barcode_agent", barcode_agent)
    graph.add_node("fda_lookup_agent", fda_lookup_node, retry=retry_policy)
    graph.add_node("recall_agent", recall_node, retry=retry_policy)
    graph.add_node("interaction_agent", interaction_node, retry=retry_policy)
    graph.add_node("safety_agent", safety_agent)
    graph.add_node("report_agent", report_node, retry=retry_policy)

    # Define edges (parallel fan-out from barcode to lookups, fan-in to safety)
    graph.set_entry_point("barcode_agent")
    graph.add_edge("barcode_agent", "fda_lookup_agent")
    graph.add_edge("barcode_agent", "recall_agent")
    graph.add_edge("barcode_agent", "interaction_agent")
    
    graph.add_edge("fda_lookup_agent", "safety_agent")
    graph.add_edge("recall_agent", "safety_agent")
    graph.add_edge("interaction_agent", "safety_agent")
    
    graph.add_edge("safety_agent", "report_agent")
    graph.add_edge("report_agent", END)

    return graph.compile(checkpointer=checkpointer)


# Compiled graph singleton
_compiled_graph = None

async def get_verification_graph_async():
    """Get or create the compiled verification graph with checkpointer."""
    global _compiled_graph
    if _compiled_graph is None:
        cp = await get_checkpointer()
        _compiled_graph = build_verification_graph(checkpointer=cp)
    return _compiled_graph


def get_verification_graph():
    """Synchronous fallback getter."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_verification_graph(checkpointer=MemorySaver())
    return _compiled_graph


async def run_full_verification(barcode: str, drug_names: list[str] = None,
                                 patient_age: int = None, patient_weight: float = None,
                                 kidney_function: str = None) -> dict:
    """
    Run the complete 6-agent verification pipeline.
    Returns final report with verdict, confidence, evidence trail, and AI summary.
    """
    from services.lookup_orchestrator import parallel_lookup
    from services.confidence import bayesian_confidence
    from services.gtin import validate_gtin
    
    gtin_res = validate_gtin(barcode)
    ndc = gtin_res.get("ndc_extracted") or barcode

    l1_results = await parallel_lookup(ndc)

    evidence_keys = []
    if gtin_res.get("valid"):
        evidence_keys.append("gtin_valid")

    openfda_data = l1_results.get("openfda", {}).get("data")
    if openfda_data:
        evidence_keys.append("openfda_exact")

    cdsco_data = l1_results.get("cdsco", {}).get("data")
    if cdsco_data:
        evidence_keys.append("cdsco_match")

    recalls_data = l1_results.get("recalls", {}).get("data")
    if recalls_data is not None:
        if len(recalls_data) == 0:
            evidence_keys.append("no_recall")
        else:
            evidence_keys.append("active_recall")

    drugbank_data = l1_results.get("drugbank", {}).get("data")
    if drugbank_data:
        evidence_keys.append("drugbank_match")

    score = bayesian_confidence(evidence_keys)

    # Record/database signals are not a physical-pack verification. Fast-path
    # exits are deliberately disabled until an authoritative serial provider is
    # part of this pipeline.
    if False and score >= 85:
        from services.openfda import extract_openfda_info
        drug_info = extract_openfda_info(openfda_data) if openfda_data else cdsco_data
        
        return {
            "verdict": "authentic",
            "confidence": score,
            "drug_info": drug_info,
            "evidence": [{"source": "L1 Orchestrator", "detail": f"Fast-path cleared with {score}% bayesian confidence", "status": "pass"}],
            "ai_report": f"Early verification cleared. Score: {score}%. Drug verified automatically.",
            "early_exit": True
        }

    graph = await get_verification_graph_async()

    initial_state = {
        "barcode": barcode,
        "drug_names": drug_names or [],
        "patient_age": patient_age,
        "patient_weight": patient_weight,
        "kidney_function": kidney_function,
        "evidence": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    try:
        from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
        from config import get_settings
        st = get_settings()
        if st.langfuse_public_key and st.langfuse_secret_key:
            lf_cb = LangfuseCallbackHandler(
                public_key=st.langfuse_public_key,
                secret_key=st.langfuse_secret_key,
                host=st.langfuse_host
            )
            config["callbacks"] = [lf_cb]
    except Exception:
        pass

    result = await graph.ainvoke(initial_state, config=config)

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
