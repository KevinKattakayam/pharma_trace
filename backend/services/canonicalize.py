import re
import httpx
import logging

logger = logging.getLogger(__name__)

NDC_PATTERNS = [
    r"^(\d{5})-(\d{4})-(\d{2})$",   # 5-4-2
    r"^(\d{5})-(\d{3})-(\d{2})$",   # 5-3-2 (most common)
    r"^(\d{4})-(\d{4})-(\d{2})$",   # 4-4-2
]

def normalize_ndc(raw: str) -> str:
    """Pad any NDC format to the 11-digit FDA canonical form."""
    raw = re.sub(r"[^0-9-]", "", raw)
    
    # Try predefined structural patterns first
    for pat in NDC_PATTERNS:
        m = re.match(pat, raw)
        if m:
            parts = [m.group(i).zfill(w) 
                     for i, w in zip([1,2,3], [5,4,2])]
            return "-".join(parts)
            
    # Fallback: strip hyphens and force 11-digit zero-pad (5-4-2 format)
    digits = re.sub(r"\D", "", raw).zfill(11)
    if len(digits) >= 11:
        return f"{digits[:5]}-{digits[5:9]}-{digits[9:11]}"
    return raw

async def map_to_rxcui(generic_name: str) -> dict:
    """
    Map Indian/International generic drug names to RxNorm Concept Unique Identifiers (RxCUI).
    This canonicalization ensures foreign generics match FDA databases.
    
    Uses NIH RxNav REST API (free, no auth required).
    """
    try:
        # First, find the RxCUI for the generic name
        async with httpx.AsyncClient() as client:
            rxnav_url = f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={generic_name}&search=1"
            res = await client.get(rxnav_url, timeout=5.0)
            
            if res.status_code == 200:
                data = res.json()
                id_group = data.get("idGroup", {})
                rxcuis = id_group.get("rxnormId")
                
                if rxcuis and len(rxcuis) > 0:
                    rxcui = rxcuis[0]
                    # Returning the canonical RxCUI, which acts as the US/FDA bridge
                    return {
                        "canonical_name": generic_name,
                        "rxcui": rxcui,
                        "mapped": True
                    }
                    
        return {
            "canonical_name": generic_name,
            "rxcui": None,
            "mapped": False
        }
    except Exception as e:
        logger.error(f"Error mapping to RxNorm: {str(e)}")
        return {
            "canonical_name": generic_name,
            "rxcui": None,
            "mapped": False
        }
