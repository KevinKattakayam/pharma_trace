"""
Entity repositories implementing VerificationRepository, AuditRepository, ReportRepository, CaregiverRepository, PharmacyRepository.
Enforces direct Supabase PostgREST access and strict RLS tenant isolation.
"""
from typing import List, Dict, Any, Optional
from repositories.base import BaseRepository


class VerificationRepository(BaseRepository):
    """Repository managing drug verifications (barcode, OCR, image scans)."""
    table_name = "verifications"

    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List verifications for a specific tenant/user aligned with Supabase RLS."""
        return await self.list_all(filters={"user_id": user_id}, limit=limit)


class AuditRepository(BaseRepository):
    """Repository managing immutable SHA-256 hash-chained audit logs."""
    table_name = "safety_check_log"

    async def get_latest_hash(self) -> Optional[str]:
        """Fetch the last hash in the audit chain."""
        records = await self.list_all(limit=1, order_by="id", order_desc=True)
        return records[0].get("audit_hash") if records else None

    async def update(self, *args, **kwargs):
        raise NotImplementedError("SECURITY VIOLATION: Audit logs are immutable and append-only. UPDATE operations are forbidden.")

    async def delete(self, *args, **kwargs):
        raise NotImplementedError("SECURITY VIOLATION: Audit logs are immutable and append-only. DELETE operations are forbidden.")



class ReportRepository(BaseRepository):
    """Repository managing anonymous zero-knowledge adverse event reports."""
    table_name = "adverse_reports"


class CaregiverRepository(BaseRepository):
    """Repository managing patient-caregiver monitoring links and telemetry alerts."""
    table_name = "caregiver_links"

    async def list_alerts_by_caregiver(self, caregiver_id: str) -> List[Dict[str, Any]]:
        rows = await self.db.query("caregiver_alerts", filters={"caregiver_id": caregiver_id}, order_by="created_at", order_desc=True)
        return rows


class PharmacyRepository(BaseRepository):
    """Repository managing verified pharmacies, reviews, and stock inventory."""
    table_name = "pharmacies"

    async def find_nearby(self, lat: float, lng: float, radius_m: int = 5000) -> List[Dict[str, Any]]:
        return await self.db.geo_query(self.table_name, lat=lat, lng=lng, radius_meters=radius_m)


class SafetyCaseRepository(BaseRepository):
    """Auditable workflow for suspected medicine incidents and quarantine actions."""
    table_name = "safety_cases"
