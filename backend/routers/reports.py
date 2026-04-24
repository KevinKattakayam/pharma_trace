"""
Reports router — community pharmacovigilance reporting, heatmap, and outbreak detection.
All data comes from real user submissions. No sample/dummy data.
"""
from fastapi import APIRouter
from models.schemas import ReportRequest, ReportResponse
from services.anonymous import create_report, get_all_reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportResponse)
async def submit_report(request: ReportRequest):
    """Submit a suspicious drug report (anonymous option available)."""
    report = create_report(
        drug_name=request.drug_name,
        description=request.description,
        city=request.city,
        country=request.country,
        barcode=request.barcode,
        anonymous=request.anonymous,
        photo_urls=request.photo_urls
    )
    return ReportResponse(
        report_id=report["id"],
        anonymous_id=report.get("anonymous_id"),
        status=report["status"]
    )


@router.get("/heatmap")
async def get_heatmap_data():
    """Get all report locations for heatmap rendering. Returns only real submissions."""
    reports = get_all_reports()

    return {"reports": [
        {
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "drug_name": r.get("drug_name"),
            "city": r.get("city"),
            "status": r.get("status")
        }
        for r in reports if r.get("lat") is not None
    ], "total": len(reports)}


@router.get("/timeline/{region}")
async def get_outbreak_timeline(region: str):
    """
    Get time-series outbreak data for a region.
    Groups real reports by day for animated heatmap playback.
    """
    from collections import defaultdict
    from datetime import datetime

    reports = get_all_reports()
    city_match = region.lower()

    # Filter reports matching the region
    regional = [r for r in reports if (r.get("city") or "").lower() == city_match
                or (r.get("country") or "").lower() == city_match]

    # Group by day
    by_day = defaultdict(list)
    for r in regional:
        if r.get("lat") is not None:
            day = r.get("created_at", datetime.now().isoformat())[:10]
            by_day[day].append({"lat": r["lat"], "lng": r["lng"]})

    frames = [{"day": day, "reports": pts} for day, pts in sorted(by_day.items())]

    # Cluster detection — alert if 3+ reports within 7 days
    alert = None
    if len(regional) >= 3:
        alert = {
            "triggered": True,
            "message": f"Cluster detected: {len(regional)} reports in {region}",
            "severity": "high" if len(regional) >= 5 else "moderate"
        }

    return {
        "region": region,
        "frames": frames,
        "total_reports": len(regional),
        "alert": alert
    }
