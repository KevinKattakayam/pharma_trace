"""
WHO GTIN / GS1 barcode validator and parser.
Validates international pharmaceutical barcodes (GTIN-8, GTIN-12, GTIN-13, GTIN-14).
Parses GS1 DataMatrix barcodes with Application Identifiers (AI) for lot, expiry, serial.
"""
import re


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


def parse_cdsco_barcode(data: str) -> dict:
    """India GSR 823(E) pack code → legacy dict shape (delegates to ``services.india_qr``).

    ``valid`` now means "recognised as a GSR 823(E) payload" (≥3 particulars). It says nothing
    about authenticity. ``complete`` is true only when all eight particulars are present.
    """
    from services import india_qr

    r = india_qr.parse(data)
    return {
        "valid": r["recognised"],
        "complete": r["complete"],
        "format": "CDSCO",
        "gtin": r["upic"],
        "upic": r["upic"],
        "brand_name": r["brand_name"],
        "generic_name": r["generic_name"],
        "manufacturer": r["manufacturer"],
        "batch_no": r["batch_no"],
        "mfg_date": r["mfg_date"],
        "expiry_date": r["expiry_date"],
        "mfg_license": r["mfg_license"],
        "mrp": r["mrp"],
        "particulars_missing": r["particulars_missing"],
        "raw": data,
    }


def parse_gs1_datamatrix(data: str) -> dict:
    """GS1 AI element string / HRI / Digital Link → legacy dict shape (delegates to ``services.gs1``)."""
    from services import gs1

    r = gs1.parse(data)
    qty = next((f["value"] for f in r["parsed_fields"] if f["ai"] == "30"), None)
    return {**r, "quantity": qty}
