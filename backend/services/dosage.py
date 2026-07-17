"""
Dosage personalizer — evaluates whether a standard dose is appropriate
based on patient age, weight, kidney function, and drug.
"""
from models.schemas import DosageAdvice, RiskLevel

async def evaluate_dosage(
    drug_name: str,
    standard_dose: str,
    age: int,
    weight_kg: float,
    kidney_function: str = "normal",
    current_dose: str = None
) -> DosageAdvice:
    """Return source label context without generating dosage recommendations.

    Personalised dosing requires a licensed clinical ruleset and clinician
    oversight. The former embedded rules and LLM classification were not a
    validated dosing engine and have been intentionally removed.
    """
    return DosageAdvice(
        standard_dose=standard_dose,
        recommended_dose="No automated dose recommendation is available.",
        risk_level=RiskLevel.unknown,
        adjustments=["Use the current approved product label and have a licensed clinician or pharmacist determine the dose."],
        warnings=["Age, weight, renal function, indication, formulation, laboratory values, and concurrent medicines require clinical review."]
    )
