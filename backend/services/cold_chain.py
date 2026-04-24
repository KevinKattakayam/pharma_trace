"""
Cold chain analysis using Open-Meteo free weather API.
Checks if temperature and humidity at a location could compromise drug integrity.
"""
import httpx
from typing import Optional


OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# WHO guidelines: most drugs should be stored at 15-25°C (59-77°F)
TEMP_MIN_C = 15.0
TEMP_MAX_C = 25.0
# Extended range for non-cold-chain drugs
TEMP_EXTENDED_MAX_C = 30.0
HUMIDITY_MAX = 75.0  # Above 75% relative humidity can damage packaging


async def check_cold_chain(lat: float, lng: float) -> dict:
    """
    Check current temperature and humidity at a location against
    pharmaceutical storage guidelines.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "latitude": lat,
                "longitude": lng,
                "current": "temperature_2m,relative_humidity_2m",
                "temperature_unit": "celsius"
            }
            resp = await client.get(OPEN_METEO_BASE, params=params)

            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m")
                humidity = current.get("relative_humidity_2m")

                if temp is None:
                    return {"available": False, "reason": "Weather data unavailable"}

                # Assess risk
                issues = []
                ok = True

                if temp > TEMP_EXTENDED_MAX_C:
                    issues.append(f"Temperature {temp}°C exceeds safe storage limit (max {TEMP_EXTENDED_MAX_C}°C)")
                    ok = False
                elif temp > TEMP_MAX_C:
                    issues.append(f"Temperature {temp}°C is above ideal storage range (15-25°C) but within extended range")
                elif temp < TEMP_MIN_C:
                    issues.append(f"Temperature {temp}°C is below recommended minimum (15°C) — freezing risk for some drugs")
                    if temp < 2:
                        ok = False

                if humidity and humidity > HUMIDITY_MAX:
                    issues.append(f"Humidity {humidity}% exceeds safe level ({HUMIDITY_MAX}%) — packaging moisture damage risk")
                    ok = False

                return {
                    "available": True,
                    "ok": ok,
                    "temperature_c": temp,
                    "humidity_pct": humidity,
                    "issues": issues,
                    "location": {"lat": lat, "lng": lng}
                }
    except Exception as e:
        return {"available": False, "reason": str(e)}

    return {"available": False, "reason": "Failed to fetch weather data"}
