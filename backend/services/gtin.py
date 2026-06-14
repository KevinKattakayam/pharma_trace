"""
WHO GTIN / GS1 barcode validator and parser.
Validates international pharmaceutical barcodes (GTIN-8, GTIN-12, GTIN-13, GTIN-14).
Parses GS1 DataMatrix barcodes with Application Identifiers (AI) for lot, expiry, serial.
"""
import re
from datetime import datetime
from typing import Optional


def validate_gtin(barcode: str) -> dict:
    """
    Validate a GTIN barcode (UPC-A, EAN-13, GTIN-14) using check digit calculation.
    Returns validation result with extracted info.
    """
    cleaned = re.sub(r'[^0-9]', '', barcode)

    result = {
        "raw_barcode": barcode,
        "cleaned": cleaned,
        "valid": False,
        "format": None,
        "check_digit_valid": False,
        "ndc_extracted": None,
        "country_prefix": None,
        "gs1_data": {}
    }

    if not cleaned:
        result["error"] = "No numeric digits found"
        return result

    length = len(cleaned)

    # Determine format
    if length == 8:
        result["format"] = "GTIN-8"
    elif length == 12:
        result["format"] = "UPC-A / GTIN-12"
    elif length == 13:
        result["format"] = "EAN-13 / GTIN-13"
    elif length == 14:
        result["format"] = "GTIN-14"
    elif length == 10 or length == 11:
        # Likely NDC format (no check digit)
        result["format"] = "NDC"
        result["valid"] = True
        result["ndc_extracted"] = cleaned
        return result
    else:
        result["error"] = f"Invalid barcode length: {length} digits"
        return result

    # Validate check digit (GS1 algorithm)
    digits = [int(d) for d in cleaned]
    check_digit = digits[-1]
    payload = digits[:-1]

    # GS1 check digit: sum of odd-position digits * 1 + even-position digits * 3
    total = 0
    for i, d in enumerate(reversed(payload)):
        total += d * (3 if i % 2 == 0 else 1)

    calculated_check = (10 - (total % 10)) % 10
    result["check_digit_valid"] = (check_digit == calculated_check)
    result["valid"] = result["check_digit_valid"]

    # Extract country prefix (first 3 digits of EAN-13 or GTIN-13)
    if length >= 13:
        prefix = cleaned[:3]
        result["country_prefix"] = prefix
        result["country"] = get_country_from_prefix(prefix)

    # Extract NDC from UPC-A (US pharma UPC starts with '3')
    if length == 12 and cleaned[0] == '3':
        # NDC is digits 1-10 (strip leading '3' and check digit)
        ndc_raw = cleaned[1:11]
        result["ndc_extracted"] = f"{ndc_raw[:5]}-{ndc_raw[5:9]}-{ndc_raw[9:]}"

    # Extract NDC from EAN-13 (US)
    if length == 13 and cleaned[:3] in ('030', '031', '032', '033', '034', '035', '036', '037', '038', '039'):
        ndc_raw = cleaned[3:13]
        result["ndc_extracted"] = f"{ndc_raw[:5]}-{ndc_raw[5:9]}-{ndc_raw[9:]}"

    return result


def parse_cdsco_barcode(data: str) -> dict:
    """
    Parse Indian CDSCO (Schedule H / Top 300) mandatory QR code format.
    Handles JSON and Pipe-delimited structures encoding the 8 mandatory fields
    specified by GSR 823(E).
    """
    result = {
        "valid": False,
        "format": "CDSCO",
        "gtin": None,
        "brand_name": None,
        "generic_name": None,
        "manufacturer": None,
        "batch_no": None,
        "mfg_date": None,
        "expiry_date": None,
        "mfg_license": None,
        "mrp": None,
        "raw": data
    }
    
    # Clean data (sometimes prepended with URLs)
    clean_data = data
    if "qr.cdsco.gov.in" in data or "http" in data:
        # Attempt to extract payload if it's base64 or URL encoded in a query param
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(data)
            qs = parse_qs(parsed_url.query)
            if 'data' in qs:
                clean_data = qs['data'][0]
            elif 'd' in qs:
                clean_data = qs['d'][0]
        except Exception:
            pass

    import json
    # Try parsing as JSON
    try:
        parsed = json.loads(clean_data)
        if isinstance(parsed, dict):
            # Map standard keys
            result["gtin"] = parsed.get("UPI") or parsed.get("GTIN") or parsed.get("upi")
            result["generic_name"] = parsed.get("API") or parsed.get("Generic") or parsed.get("api")
            result["brand_name"] = parsed.get("Brand") or parsed.get("brand")
            result["manufacturer"] = parsed.get("Mfg") or parsed.get("Manufacturer") or parsed.get("mfg")
            result["batch_no"] = parsed.get("Batch") or parsed.get("batch") or parsed.get("Lot")
            result["mfg_date"] = parsed.get("MFD") or parsed.get("mfd") or parsed.get("MfgDate")
            result["expiry_date"] = parsed.get("EXP") or parsed.get("exp") or parsed.get("ExpDate")
            result["mfg_license"] = parsed.get("Lic") or parsed.get("lic") or parsed.get("License")
            result["mrp"] = parsed.get("MRP") or parsed.get("mrp") or parsed.get("Price")
            
            # G.S.R. 823(E) requires all 8 mandatory fields:
            # UPI/GTIN, generic name, batch, expiry, mfg date, MRP, manufacturer, brand
            mandatory = [
                result["gtin"], result["generic_name"], result["batch_no"],
                result["expiry_date"], result["mfg_date"], result["manufacturer"],
                result["brand_name"], result["mrp"]
            ]
            if all(mandatory):
                result["valid"] = True
                return result
            # Incomplete — fall through to GS1 pipeline
    except json.JSONDecodeError:
        pass

    # Try parsing as Pipe-delimited (UPI|Generic|Brand|Mfg|Batch|MFD|EXP|MRP|Lic)
    parts = clean_data.split('|')
    if len(parts) >= 8:
        result["gtin"] = parts[0]
        result["generic_name"] = parts[1]
        result["brand_name"] = parts[2]
        result["manufacturer"] = parts[3]
        result["batch_no"] = parts[4]
        result["mfg_date"] = parts[5]
        result["expiry_date"] = parts[6]
        result["mrp"] = parts[7]
        if len(parts) > 8:
            result["mfg_license"] = parts[8]
            
        # Strict: all 8 mandatory fields must be present and non-empty
        mandatory = [
            result["gtin"], result["generic_name"], result["batch_no"],
            result["expiry_date"], result["mfg_date"], result["manufacturer"],
            result["brand_name"], result["mrp"]
        ]
        if all(f and str(f).strip() for f in mandatory):
            result["valid"] = True
            return result
        # Incomplete — fall through

    return result

def parse_gs1_datamatrix(data: str) -> dict:
    """
    Parse GS1 DataMatrix or GS1-128 barcode data with Application Identifiers.
    Common pharmaceutical AIs:
    - (01) GTIN
    - (10) Batch/Lot number
    - (17) Expiry date (YYMMDD)
    - (21) Serial number
    - (30) Quantity
    """
    result = {
        "raw": data,
        "gtin": None,
        "lot": None,
        "expiry_date": None,
        "serial_number": None,
        "quantity": None,
        "parsed_fields": []
    }

    # Remove FNC1 character if present
    cleaned = data.replace('\x1d', '|').replace('\\x1d', '|')

    # AI patterns (fixed-length and variable-length)
    ai_patterns = {
        "01": {"name": "GTIN", "length": 14, "key": "gtin"},
        "10": {"name": "Batch/Lot", "length": None, "key": "lot"},
        "17": {"name": "Expiry Date", "length": 6, "key": "expiry_date"},
        "21": {"name": "Serial Number", "length": None, "key": "serial_number"},
        "30": {"name": "Quantity", "length": None, "key": "quantity"},
    }

    pos = 0
    while pos < len(cleaned):
        matched = False
        # Try 2-digit AIs
        for ai_code, ai_info in ai_patterns.items():
            if cleaned[pos:pos + len(ai_code)] == ai_code:
                pos += len(ai_code)
                if ai_info["length"]:
                    value = cleaned[pos:pos + ai_info["length"]]
                    pos += ai_info["length"]
                else:
                    # Variable length — read until FNC1 separator or end
                    end = cleaned.find('|', pos)
                    if end == -1:
                        end = len(cleaned)
                    value = cleaned[pos:end]
                    pos = end + 1

                result[ai_info["key"]] = value
                result["parsed_fields"].append({
                    "ai": ai_code,
                    "name": ai_info["name"],
                    "value": value
                })
                matched = True
                break

        if not matched:
            pos += 1

    # Parse expiry date
    if result["expiry_date"] and len(result["expiry_date"]) == 6:
        try:
            yy = int(result["expiry_date"][:2])
            mm = int(result["expiry_date"][2:4])
            dd = int(result["expiry_date"][4:6]) or 28
            year = 2000 + yy
            expiry = datetime(year, mm, min(dd, 28))
            result["expiry_parsed"] = expiry.strftime("%Y-%m-%d")
            result["expired"] = expiry < datetime.now()
        except (ValueError, OverflowError):
            pass

    return result


def get_country_from_prefix(prefix: str) -> str:
    """Map GS1 prefix to country of registration."""
    prefix_map = {
        "000": "United States", "001": "United States", "002": "United States",
        "003": "United States", "004": "United States", "005": "United States",
        "006": "United States", "007": "United States", "008": "United States",
        "009": "United States",
        "030": "United States (Pharma)", "031": "United States (Pharma)",
        "032": "United States (Pharma)", "033": "United States (Pharma)",
        "034": "United States (Pharma)", "035": "United States (Pharma)",
        "036": "United States (Pharma)", "037": "United States (Pharma)",
        "038": "United States (Pharma)", "039": "United States (Pharma)",
        "040": "Germany", "041": "Germany", "042": "Germany", "043": "Germany",
        "044": "Germany",
        "300": "France", "301": "France", "302": "France", "303": "France",
        "380": "Bulgaria", "383": "Slovenia",
        "400": "Germany", "401": "Germany", "402": "Germany",
        "450": "Japan", "451": "Japan", "452": "Japan", "453": "Japan",
        "460": "Russia", "461": "Russia", "462": "Russia",
        "471": "Taiwan",
        "489": "Hong Kong",
        "490": "Japan", "491": "Japan", "492": "Japan",
        "500": "United Kingdom", "501": "United Kingdom", "502": "United Kingdom",
        "503": "United Kingdom", "504": "United Kingdom", "505": "United Kingdom",
        "506": "United Kingdom", "507": "United Kingdom", "508": "United Kingdom",
        "509": "United Kingdom",
        "520": "Greece", "528": "Lebanon", "529": "Cyprus",
        "530": "Albania", "531": "Macedonia",
        "535": "Malta", "539": "Ireland",
        "540": "Belgium", "541": "Belgium", "542": "Belgium",
        "543": "Belgium", "544": "Belgium", "545": "Belgium",
        "546": "Belgium", "547": "Belgium", "548": "Belgium",
        "549": "Belgium",
        "560": "Portugal",
        "569": "Iceland",
        "570": "Denmark", "571": "Denmark", "572": "Denmark",
        "573": "Denmark", "574": "Denmark", "575": "Denmark",
        "576": "Denmark", "577": "Denmark", "578": "Denmark",
        "579": "Denmark",
        "590": "Poland",
        "594": "Romania",
        "599": "Hungary",
        "600": "South Africa", "601": "South Africa",
        "608": "Bahrain",
        "609": "Mauritius",
        "611": "Morocco",
        "613": "Algeria",
        "615": "Nigeria",
        "616": "Kenya",
        "618": "Ivory Coast",
        "619": "Tunisia",
        "621": "Syria",
        "622": "Egypt",
        "624": "Libya",
        "625": "Jordan",
        "626": "Iran",
        "627": "Kuwait",
        "628": "Saudi Arabia",
        "629": "UAE",
        "690": "China", "691": "China", "692": "China",
        "693": "China", "694": "China", "695": "China",
        "696": "China", "697": "China", "698": "China",
        "699": "China",
        "700": "Norway", "701": "Norway", "702": "Norway",
        "703": "Norway", "704": "Norway", "705": "Norway",
        "706": "Norway", "707": "Norway", "708": "Norway",
        "709": "Norway",
        "729": "Israel",
        "730": "Sweden", "731": "Sweden", "732": "Sweden",
        "733": "Sweden", "734": "Sweden", "735": "Sweden",
        "736": "Sweden", "737": "Sweden", "738": "Sweden",
        "739": "Sweden",
        "740": "Guatemala", "741": "El Salvador", "742": "Honduras",
        "743": "Nicaragua", "744": "Costa Rica", "745": "Panama",
        "746": "Dominican Republic", "750": "Mexico",
        "754": "Canada", "755": "Canada",
        "759": "Venezuela",
        "760": "Switzerland", "761": "Switzerland", "762": "Switzerland",
        "770": "Colombia",
        "773": "Uruguay",
        "775": "Peru",
        "777": "Bolivia",
        "778": "Argentina", "779": "Argentina",
        "780": "Chile",
        "784": "Paraguay",
        "786": "Ecuador",
        "789": "Brazil", "790": "Brazil",
        "800": "Italy", "801": "Italy", "802": "Italy",
        "803": "Italy", "804": "Italy", "805": "Italy",
        "806": "Italy", "807": "Italy", "808": "Italy",
        "809": "Italy",
        "840": "Spain", "841": "Spain", "842": "Spain",
        "843": "Spain", "844": "Spain", "845": "Spain",
        "846": "Spain", "847": "Spain", "848": "Spain",
        "849": "Spain",
        "850": "Cuba",
        "858": "Slovakia",
        "859": "Czech Republic",
        "860": "Serbia",
        "865": "Mongolia",
        "867": "North Korea",
        "868": "Turkey", "869": "Turkey",
        "870": "Netherlands", "871": "Netherlands", "872": "Netherlands",
        "873": "Netherlands", "874": "Netherlands", "875": "Netherlands",
        "876": "Netherlands", "877": "Netherlands", "878": "Netherlands",
        "879": "Netherlands",
        "880": "South Korea",
        "884": "Cambodia",
        "885": "Thailand",
        "888": "Singapore",
        "890": "India",
        "893": "Vietnam",
        "896": "Pakistan",
        "899": "Indonesia",
        "900": "Austria", "901": "Austria", "902": "Austria",
        "903": "Austria", "904": "Austria", "905": "Austria",
        "906": "Austria", "907": "Austria", "908": "Austria",
        "909": "Austria",
        "930": "Australia", "931": "Australia", "932": "Australia",
        "933": "Australia", "934": "Australia", "935": "Australia",
        "936": "Australia", "937": "Australia", "938": "Australia",
        "939": "Australia",
        "940": "New Zealand", "941": "New Zealand", "942": "New Zealand",
        "943": "New Zealand", "944": "New Zealand", "945": "New Zealand",
        "946": "New Zealand", "947": "New Zealand", "948": "New Zealand",
        "949": "New Zealand",
        "955": "Malaysia",
        "958": "Macau",
    }
    return prefix_map.get(prefix, f"Unknown (prefix {prefix})")
