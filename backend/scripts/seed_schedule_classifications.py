import asyncio
from services.supabase import get_supabase

# Representative sample of Schedule H/H1/X drugs from CDSCO
SCHEDULED_DRUGS = [
    # Schedule H1 (Strictly restricted, habit-forming, or broad-spectrum antibiotics)
    {"generic_name": "alprazolam", "schedule": "H1"},
    {"generic_name": "buprenorphine", "schedule": "H1"},
    {"generic_name": "cefixime", "schedule": "H1"},
    {"generic_name": "codeine", "schedule": "H1"},
    {"generic_name": "diazepam", "schedule": "H1"},
    {"generic_name": "diphenoxylate", "schedule": "H1"},
    {"generic_name": "fentanyl", "schedule": "H1"},
    {"generic_name": "ketamine", "schedule": "H1"},
    {"generic_name": "lorazepam", "schedule": "H1"},
    {"generic_name": "midazolam", "schedule": "H1"},
    {"generic_name": "moxifloxacin", "schedule": "H1"},
    {"generic_name": "tramadol", "schedule": "H1"},
    {"generic_name": "zolpidem", "schedule": "H1"},

    # Schedule H (Prescription only)
    {"generic_name": "amoxicillin", "schedule": "H"},
    {"generic_name": "azithromycin", "schedule": "H"},
    {"generic_name": "diclofenac", "schedule": "H"},
    {"generic_name": "ibuprofen", "schedule": "H"}, # Higher doses/combinations are H in India
    {"generic_name": "metformin", "schedule": "H"},
    {"generic_name": "naproxen", "schedule": "H"},
    {"generic_name": "omeprazole", "schedule": "H"},
    {"generic_name": "pantoprazole", "schedule": "H"},

    # Schedule X (Narcotics and psychotropics)
    {"generic_name": "amobarbital", "schedule": "X"},
    {"generic_name": "amphetamine", "schedule": "X"},
    {"generic_name": "dexamphetamine", "schedule": "X"},
    {"generic_name": "methamphetamine", "schedule": "X"},
    {"generic_name": "methylphenidate", "schedule": "X"},
    {"generic_name": "secobarbital", "schedule": "X"},
    
    # Explicitly OTC / GSL
    {"generic_name": "paracetamol", "schedule": "OTC"},
    {"generic_name": "acetaminophen", "schedule": "OTC"},
    {"generic_name": "cetirizine", "schedule": "OTC"},
    {"generic_name": "levocetirizine", "schedule": "OTC"},
    {"generic_name": "loratadine", "schedule": "OTC"},
    {"generic_name": "fexofenadine", "schedule": "OTC"},
    {"generic_name": "aspirin", "schedule": "OTC"},
    {"generic_name": "dextromethorphan", "schedule": "OTC"},
    {"generic_name": "guaifenesin", "schedule": "OTC"},
    {"generic_name": "ambroxol", "schedule": "OTC"},
    {"generic_name": "simethicone", "schedule": "OTC"},
    {"generic_name": "loperamide", "schedule": "OTC"},
    {"generic_name": "domperidone", "schedule": "OTC"},
    {"generic_name": "ondansetron", "schedule": "H"}, # Usually Rx in India
    {"generic_name": "meclizine", "schedule": "OTC"},
]

async def seed_classifications():
    db = get_supabase()
    if not db.available:
        print("Database not available. Make sure SUPABASE_URL and SUPABASE_KEY are set.")
        return
        
    print(f"Seeding {len(SCHEDULED_DRUGS)} schedule classifications...")
    
    success_count = 0
    error_count = 0
    
    for drug in SCHEDULED_DRUGS:
        try:
            # We use upsert to avoid duplicate errors on re-run
            await db.insert("schedule_classifications", {
                "generic_name": drug["generic_name"].lower(),
                "schedule": drug["schedule"],
                "source": "cdsco_manual_seed"
            }, upsert=True)
            success_count += 1
        except Exception as e:
            print(f"Failed to insert {drug['generic_name']}: {e}")
            error_count += 1
            
    print(f"Seeding complete! Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    asyncio.run(seed_classifications())
