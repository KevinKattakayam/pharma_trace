import asyncio
from services.openfda import get_drug_label
from services.cold_chain import extract_storage_temp

async def test():
    drugs = ["ibuprofen", "amoxicillin", "lisinopril", "levothyroxine", "insulin"]
    for d in drugs:
        label = await get_drug_label(drug_name=d)
        min_t, max_t = extract_storage_temp(label)
        print(f"{d.ljust(15)} : {min_t}°C to {max_t}°C")

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
    asyncio.run(test())
