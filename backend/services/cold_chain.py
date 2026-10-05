"""
Cold chain analysis using Open-Meteo free weather API.
Checks if temperature and humidity at a location could compromise drug integrity.
"""
import re

import httpx

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# WHO guidelines: most drugs should be stored at 15-25°C (59-77°F)
TEMP_MIN_C = 15.0
TEMP_MAX_C = 25.0
# Extended range for non-cold-chain drugs
TEMP_EXTENDED_MAX_C = 30.0
HUMIDITY_MAX = 75.0  # Above 75% relative humidity can damage packaging

def extract_storage_temp(label: dict) -> tuple[float, float]:
    """Extract storage temperature from OpenFDA label."""
    if not label:
        return TEMP_MIN_C, TEMP_EXTENDED_MAX_C
    
    storage_text = ""
    if "storage_and_handling" in label:
        storage_text = " ".join(label["storage_and_handling"]).lower()
    elif "how_supplied" in label:
        storage_text = " ".join(label["how_supplied"]).lower()
        
    if not storage_text:
        return TEMP_MIN_C, TEMP_EXTENDED_MAX_C

    min_t = TEMP_MIN_C
    max_t = TEMP_EXTENDED_MAX_C

    def f_to_c(f):
        return round((f - 32) * 5.0 / 9.0, 1)

    # 1. Check for explicit ranges: "20° to 25°C", "20°C to 25°C", "68 to 77 F"
    range_match = re.search(r"(\d+)[°\sCcfF]*(to|-)\s*(\d+)[°\s]*([cf])", storage_text)
    if range_match:
        val1 = float(range_match.group(1))
        val2 = float(range_match.group(3))
        unit = range_match.group(4)
        if unit == 'f':
            return f_to_c(val1), f_to_c(val2)
        return val1, val2

    # 2. Check for "below 30 C" or "below 86 F"
    below_match = re.search(r"below\s*(\d+)[°\s]*([cf])", storage_text)
    if below_match:
        val = float(below_match.group(1))
        unit = below_match.group(2)
        max_t = f_to_c(val) if unit == 'f' else val
        return min_t, max_t

    # 3. Check for fridge conditions
    if "refrigerat" in storage_text or "2 to 8" in storage_text or "36 to 46" in storage_text:
        return 2.0, 8.0

    # 4. Check for "do not freeze"
    if "do not freeze" in storage_text:
        min_t = max(min_t, 2.0)
        
    return min_t, max_t

async def check_cold_chain(lat: float, lng: float, label: dict = None) -> dict:
    """
    Check current temperature and humidity at a location against
    pharmaceutical storage guidelines.
    """
    min_temp, max_temp = extract_storage_temp(label)
    
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

                if temp > max_temp:
                    issues.append(f"Temperature {temp}°C exceeds safe storage limit (max {max_temp}°C)")
                    ok = False
                elif temp < min_temp:
                    issues.append(f"Temperature {temp}°C is below recommended minimum ({min_temp}°C) — freezing risk")
                    if temp < min_temp - 5:
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
