"""Run labelled cases through the real pipeline. Only counts outcomes; never invents metrics."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _verify(case: dict) -> dict:
    import routers.verify as v
    from models.schemas import BarcodeVerifyRequest

    s = {"ndc": None, "cdsco_drug": None, "fda": [], "cdsco": {"available": True}, "serial": {"verified": None}} | case.get("stubs", {})

    def const(value):
        async def _f(*_a, **_k):
            return value
        return _f
    patches = {"lookup_by_ndc": const(s["ndc"]), "lookup_indian_drug": const(s["cdsco_drug"]),
               "resolve_drug_name": const({"source": "unresolved"}), "check_recalls": const(s["fda"]),
               "check_cdsco_recall": const(s["cdsco"]), "get_drug_label": const(None),
               "check_drug_shortage": const({"in_shortage": False}), "verify_serialized_package": const(s["serial"])}
    saved = {k: getattr(v, k) for k in patches}
    try:
        for k, fn in patches.items():
            setattr(v, k, fn)
        res = await v.verify_barcode_core(BarcodeVerifyRequest(**case["input"]), None)
    finally:
        for k, fn in saved.items():
            setattr(v, k, fn)
    return {"verdict": res.verdict, "reasons": res.verdict_reasons}


def _run(case: dict) -> dict:
    if case["endpoint"] == "pack_check":
        from services.pack_check import check_pack
        r = check_pack(**case["input"])
        return {"status": r["status"], "reasons": r["integrity_flags"]}
    if case["endpoint"] == "lasa":
        from services.lasa import check_name
        r = check_name(**case["input"])
        return {"status": r["status"], "reasons": [w["similar_name"] for w in r["warnings"]]}
    return asyncio.run(_verify(case))


def evaluate(path: Path, allow_synthetic: bool) -> dict:
    data = json.loads(path.read_text())
    if data.get("synthetic") and not allow_synthetic:
        raise SystemExit("Refusing to report on synthetic data without --allow-synthetic.")
    tally: Counter[str] = Counter()
    failures = []
    for case in data["cases"]:
        got, exp = _run(case), case["expected"]
        ok = (exp.get("verdict") in (None, got.get("verdict")) and exp.get("status") in (None, got.get("status"))
              and set(exp.get("reasons_include", [])) <= set(got.get("reasons", []))
              and not set(exp.get("reasons_exclude", [])) & set(got.get("reasons", [])))
        tally["pass" if ok else "fail"] += 1
        if not ok:
            failures.append({"id": case["id"], "expected": exp, "got": got})
    label = "SYNTHETIC SMOKE TEST, NOT A BENCHMARK" if data.get("synthetic") else "labelled set"
    return {"dataset": str(path), "label": label, "cases": len(data["cases"]), "pass": tally["pass"], "fail": tally["fail"], "failures": failures}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", type=Path)
    ap.add_argument("--allow-synthetic", action="store_true")
    a = ap.parse_args()
    print(json.dumps(evaluate(a.cases, a.allow_synthetic), indent=2))
