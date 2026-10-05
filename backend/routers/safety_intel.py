"""Safety intelligence endpoints: Pack Check, regulator batch alerts, LASA name guard.

All three are feature-flagged (``FEATURE_PACK_CHECK``, ``FEATURE_BATCH_ALERTS``,
``FEATURE_LASA_GUARD``) and return 404 when disabled.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.requests import Request

from config import get_settings
from models.schemas import LasaCheckRequest, PackCheckRequest, PriceCheckRequest
from services.limiter import limiter

router = APIRouter(prefix="/safety", tags=["safety-intelligence"])


def _require(flag: str) -> None:
    if not getattr(get_settings(), flag):
        raise HTTPException(status_code=404, detail="Feature disabled")


@router.post("/pack-check")
@limiter.limit("30/minute")
async def pack_check(request: Request, body: PackCheckRequest) -> dict[str, Any]:
    """Check a pack's QR/DataMatrix against its printed label, date logic and regulator alerts.

    Returns consistent / inconsistent / incomplete / insufficient_data. Never "authentic".
    """
    _require("feature_pack_check")
    if not body.qr_payload and not (body.printed and any(body.printed.model_dump().values())):
        raise HTTPException(status_code=422, detail="Provide qr_payload and/or printed label fields")
    from services.pack_check import check_pack
    return check_pack(qr_payload=body.qr_payload, printed=body.printed.model_dump() if body.printed else None,
                      units_in_pack=body.units_in_pack)


@router.get("/batch-alerts")
@limiter.limit("60/minute")
async def batch_alerts(
    request: Request,
    batch: str = Query(..., min_length=1, max_length=40),
    product: str | None = Query(None, max_length=200),
    generic: str | None = Query(None, max_length=200),
) -> dict[str, Any]:
    """Look up a batch number in loaded regulator alerts (CDSCO NSQ / spurious lists)."""
    _require("feature_batch_alerts")
    from services.batch_alerts import get_index
    return get_index().match(batch, product, generic)


@router.get("/batch-alerts/coverage")
async def batch_alerts_coverage() -> dict[str, Any]:
    """Which alert months are loaded, from where, and whether the data is a sample."""
    _require("feature_batch_alerts")
    from services.batch_alerts import get_index
    return get_index().coverage()


@router.post("/price-check")
@limiter.limit("60/minute")
async def price_check(request: Request, body: PriceCheckRequest) -> dict[str, Any]:
    """Compare a printed MRP with the NPPA ceiling price for scheduled (essential) medicines."""
    _require("feature_price_check")
    from services.price_check import check_price
    return check_price(drug_name=body.drug_name, printed_mrp=body.printed_mrp, units_in_pack=body.units_in_pack,
                       dosage_form=body.dosage_form, strength=body.strength)


@router.get("/price-check/coverage")
async def price_check_coverage() -> dict[str, Any]:
    """Which ceiling-price data is loaded, from where, and whether it is sample data."""
    _require("feature_price_check")
    from services.price_check import get_index
    return get_index().coverage()


@router.post("/lasa-check")
@limiter.limit("60/minute")
async def lasa_check(request: Request, body: LasaCheckRequest) -> dict[str, Any]:
    """Warn when a medicine name looks or sounds like a registered name with different ingredients."""
    _require("feature_lasa_guard")
    import asyncio

    from services.lasa import check_name
    # CPU-bound fuzzy matching runs off the event loop so it cannot stall other requests.
    return await asyncio.to_thread(check_name, body.name, body.generic_name)
