"""
Supabase database client initialization.
Uses Supabase free tier (PostgreSQL + PostGIS) for persistent storage.
Falls back to in-memory storage when Supabase credentials are not configured.
"""
import httpx
from typing import Optional
from config import get_settings


class SupabaseClient:
    """
    Lightweight Supabase REST client (no heavy SDK dependency).
    Uses Supabase PostgREST API directly.
    """

    def __init__(self):
        settings = get_settings()
        self.url = settings.supabase_url.rstrip('/') if settings.supabase_url else ""
        self.key = settings.supabase_key
        self.available = bool(self.url and self.key)

    @property
    def headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def query(self, table: str, select: str = "*", filters: dict = None, limit: int = 100) -> list:
        """Query a Supabase table via PostgREST."""
        if not self.available:
            return []

        try:
            params = {"select": select, "limit": str(limit)}
            if filters:
                for key, value in filters.items():
                    params[key] = f"eq.{value}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/rest/v1/{table}",
                    headers=self.headers,
                    params=params
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return []

    async def insert(self, table: str, data: dict) -> Optional[dict]:
        """Insert a row into a Supabase table."""
        if not self.available:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.url}/rest/v1/{table}",
                    headers=self.headers,
                    json=data
                )
                if resp.status_code in (200, 201):
                    result = resp.json()
                    return result[0] if isinstance(result, list) and result else result
        except Exception:
            pass
        return None

    async def insert_many(self, table: str, rows: list[dict]) -> list:
        """Insert multiple rows into a Supabase table."""
        if not self.available:
            return []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.url}/rest/v1/{table}",
                    headers=self.headers,
                    json=rows
                )
                if resp.status_code in (200, 201):
                    return resp.json()
        except Exception:
            pass
        return []

    async def rpc(self, function_name: str, params: dict = None) -> Optional[dict]:
        """Call a Supabase RPC (stored function)."""
        if not self.available:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.url}/rest/v1/rpc/{function_name}",
                    headers=self.headers,
                    json=params or {}
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    async def geo_query(self, table: str, lat: float, lng: float, radius_meters: int = 5000) -> list:
        """
        Query using PostGIS ST_DWithin (requires PostGIS extension and geography column).
        Table must have a 'location' column of type geography(Point, 4326).
        """
        if not self.available:
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.url}/rest/v1/rpc/nearby_{table}",
                    headers=self.headers,
                    json={
                        "lat": lat,
                        "lng": lng,
                        "radius_m": radius_meters
                    }
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return []


# Singleton instance
_client: Optional[SupabaseClient] = None


def get_supabase() -> SupabaseClient:
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
