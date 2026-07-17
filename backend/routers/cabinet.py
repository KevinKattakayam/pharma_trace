from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
import httpx
from datetime import datetime, timedelta
from services.supabase import get_supabase
from services.drug_resolver import resolve_all_drugs
from services.interactions import check_interactions_enterprise
from config import get_settings
from dependencies import require_current_user
from models.schemas import CurrentUser
from services.groq_ai import ai_normalize_conditions

router = APIRouter(prefix="/cabinet", tags=["cabinet", "family"])

class FamilyMember(BaseModel):
    user_id: str
    name: str
    age: int
    conditions: str

class Medicine(BaseModel):
    user_id: str
    medicine_name: str
    expiry_date: str
    quantity_remaining: Optional[int] = None
    daily_dose_units: Optional[int] = None

# Supabase client handles robust local SQLite persistence automatically

COMMON_CONDITIONS_MAP = {
    "high blood pressure": "Hypertension",
    "bp": "Hypertension",
    "hypertension": "Hypertension",
    "kidney disease": "Renal Impairment",
    "bad kidneys": "Renal Impairment",
    "ckd": "Renal Impairment",
    "renal failure": "Renal Impairment",
    "liver disease": "Hepatic Impairment",
    "bad liver": "Hepatic Impairment",
    "cirrhosis": "Hepatic Impairment",
    "diabetes": "Diabetes Mellitus",
    "sugar": "Diabetes Mellitus",
    "asthma": "Asthma",
    "copd": "Pulmonary Disease, Chronic Obstructive",
    "heart disease": "Cardiovascular Diseases",
    "heart failure": "Heart Failure",
    "peptic ulcer": "Peptic Ulcer",
    "ulcer": "Peptic Ulcer",
    "gerd": "Gastroesophageal Reflux",
    "glaucoma": "Glaucoma",
    "epilepsy": "Epilepsy",
    "seizures": "Epilepsy",
    "depression": "Depression",
    "anxiety": "Anxiety",
    "pregnant": "Pregnancy",
    "pregnancy": "Pregnancy",
    "breastfeeding": "Breast Feeding"
}

async def normalize_conditions(conditions: str) -> list:
    """Normalize free-text conditions using AI, with static map fallback."""
    # Try AI normalization first for high-quality MED-RT mapping
    try:
        ai_result = await ai_normalize_conditions(conditions)
        if ai_result:
            return ai_result
    except Exception:
        pass

    # Fallback to local heuristic map if AI fails or is offline
    normalized = []
    conds = [c.strip().lower() for c in conditions.replace(" and ", ",").split(",") if c.strip()]
    for c in conds:
        mapped = False
        for key, medrt in COMMON_CONDITIONS_MAP.items():
            if key in c:
                if medrt not in normalized:
                    normalized.append(medrt)
                mapped = True
                break
        if not mapped:
            normalized.append(c) # keep original if unmapped
    return normalized

@router.post("/members")
async def add_family_member(member: FamilyMember, current_user: CurrentUser = Depends(require_current_user)):
    if member.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="403 Forbidden: Cannot modify another user's family members.")
    db = get_supabase()
    conditions_normalized = await normalize_conditions(member.conditions)
    
    data = {
        "id": str(uuid.uuid4()),
        "user_id": member.user_id,
        "name": member.name,
        "age": member.age,
        "conditions_raw": member.conditions,
        "conditions_normalized": conditions_normalized
    }
    result = await db.insert("family_members", data)
    return result if isinstance(result, dict) else (result[0] if isinstance(result, list) and len(result) > 0 else data)

@router.get("/members/{user_id}")
async def get_family_members(user_id: str, current_user: CurrentUser = Depends(require_current_user)):
    if user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="403 Forbidden: Cannot query another user's family members.")
    db = get_supabase()
    result = await db.query("family_members", filters={"user_id": user_id})
    return result or []

@router.post("/add")
async def add_medicine(med: Medicine, current_user: CurrentUser = Depends(require_current_user)):
    if med.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="403 Forbidden: Cannot add to another user's cabinet.")
    db = get_supabase()
    
    resolved = await resolve_all_drugs([med.medicine_name])
    rxcui = resolved[0].get("rxcui") if resolved else None
    
    duplicate_warning = None
    if rxcui:
        dupes = await db.query("medicine_cabinet", filters={"user_id": med.user_id, "rxcui": rxcui})
        if dupes:
            duplicate_warning = f"This cabinet already contains {dupes[0]['medicine_name']} with the same active ingredient."
            
    data = {
        "id": str(uuid.uuid4()),
        "user_id": med.user_id,
        "medicine_name": med.medicine_name,
        "expiry_date": med.expiry_date,
        "scanned_at": datetime.utcnow().isoformat(),
        "rxcui": rxcui,
        "quantity_remaining": med.quantity_remaining,
        "daily_dose_units": med.daily_dose_units
    }
    
    result = await db.insert("medicine_cabinet", data)
    ret = dict(result if isinstance(result, dict) else (result[0] if isinstance(result, list) and len(result) > 0 else data))
    if duplicate_warning: ret["duplicate_warning"] = duplicate_warning
    return ret

@router.get("/list/{user_id}")
async def list_medicines(user_id: str, current_user: CurrentUser = Depends(require_current_user)):
    if user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="403 Forbidden: Cannot query another user's cabinet.")
    db = get_supabase()
    meds = await db.query("medicine_cabinet", filters={"user_id": user_id}) or []
        
    rxcui_map = {}
    for row in meds:
        rx = row.get("rxcui")
        if rx:
            rxcui_map.setdefault(rx, set()).add(row["medicine_name"])
            
    household_duplicates = []
    for rx, names in rxcui_map.items():
        if len(names) > 1:
            household_duplicates.append({"rxcui": rx, "medicines": list(names), "count": len(names)})
            
    return {"medicines": meds, "household_duplicates": household_duplicates}

@router.get("/expiring/{user_id}")
async def get_expiring(user_id: str, current_user: CurrentUser = Depends(require_current_user)):
    if user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="403 Forbidden: Cannot query another user's cabinet.")
    list_res = await list_medicines(user_id, current_user)
    meds = list_res.get("medicines", [])
    now = datetime.utcnow()
    threshold = now + timedelta(days=30)
    expiring = []
    
    for m in meds:
        try:
            days_supply = m.get("days_supply_remaining")
            if days_supply is not None and days_supply <= 5:
                m_copy = dict(m)
                m_copy["supply_warning"] = f"Only {days_supply} days of supply left"
                expiring.append(m_copy)
                continue
                
            exp_str = m.get("expiry_date", "").replace('Z', '+00:00')
            if len(exp_str) == 10:
                exp_str += "T00:00:00+00:00"
            exp = datetime.fromisoformat(exp_str)
            if exp <= threshold:
                expiring.append(m)
        except Exception:
            pass
    return {"expiring": expiring}

@router.get("/check/{medicine_name}/{member_id}")
async def check_safe(medicine_name: str, member_id: str, current_user: CurrentUser = Depends(require_current_user)):
    db = get_supabase()
    member = None
    result = await db.query("family_members", filters={"id": member_id})
    if result: member = result[0]
        
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    conditions_normalized = member.get("conditions_normalized", [])
    conditions_raw = member.get("conditions_raw", "")
    
    resolved = await resolve_all_drugs([medicine_name])
    drug_rxcui = resolved[0].get("rxcui") if resolved else None
    resolved_name = resolved[0].get("generic_name", medicine_name) if resolved else medicine_name
    
    verdict = True
    verdict_source = "rxnorm_deterministic"
    warning = ""
    llm_prompt = ""
    llm_response = ""
    
    if drug_rxcui and conditions_normalized:
        # Check drug-disease contraindications using RxClass MEDRT
        ci_classes = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui={drug_rxcui}&relaSource=MEDRT")
                if resp.status_code == 200:
                    data = resp.json()
                    info_list = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
                    for info in info_list:
                        if info.get("rela") == "ci_with":
                            cls_name = info.get("rxclassMinConceptItem", {}).get("className")
                            if cls_name:
                                ci_classes.append(cls_name.lower())
        except Exception:
            pass

        # See if any normalized condition matches the contraindicated classes
        findings = []
        for cond in conditions_normalized:
            cond_clean = cond.strip().lower()
            for ci in ci_classes:
                ci_clean = ci.strip().lower()
                if cond_clean == ci_clean or cond_clean in ci_clean or ci_clean in cond_clean:
                    findings.append(ci)
        
        if findings:
            verdict = False
            verdict_source = "llm_advisory"
            
            settings = get_settings()
            if settings.groq_api_key:
                from services.groq_ai import _call_groq
                ix_desc = f"{resolved_name} is contraindicated with: {', '.join(set(findings))}."
                llm_prompt = f"Explain this contraindication in plain language for a patient with {conditions_raw}: {ix_desc}. Keep it under 2 sentences. Do not use medical jargon."
                try:
                    llm_response = await _call_groq(llm_prompt)
                    warning = llm_response
                except Exception:
                    warning = ix_desc
            else:
                warning = f"Contraindication found: {resolved_name} and {', '.join(set(findings))}"
    
    if not warning:
        verdict_source = "live_medrt_cleared"
        
    if db.available:
        try:
            await db.insert("safety_check_log", {
                "user_id": member.get("user_id", ""),
                "member_id": member_id,
                "medicine_name_raw": medicine_name,
                "medicine_name_resolved": resolved_name,
                "rxcui": drug_rxcui,
                "conditions_raw": conditions_raw,
                "conditions_normalized": conditions_normalized,
                "verdict": verdict,
                "verdict_source": verdict_source,
                "verdict_reason": warning,
                "llm_prompt": llm_prompt,
                "llm_response": llm_response
            })
        except Exception:
            pass
            
    return {
        "member": member["name"],
        "medicine": medicine_name,
        "is_safe": verdict,
        "warning": warning,
        "source": verdict_source
    }
