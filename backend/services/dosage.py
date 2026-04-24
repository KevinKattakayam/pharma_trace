"""
Dosage personalizer — evaluates whether a standard dose is appropriate
based on patient age, weight, kidney function, and drug.
"""
from models.schemas import DosageAdvice, RiskLevel


def evaluate_dosage(
    drug_name: str,
    standard_dose: str,
    age: int,
    weight_kg: float,
    kidney_function: str = "normal",
    current_dose: str = None
) -> DosageAdvice:
    """
    Evaluates dosage safety based on patient characteristics.

    Flags:
    - Geriatric (age > 65): many drugs need dose reduction
    - Pediatric (age < 12): mg/kg dosing required
    - Renal impairment: drugs cleared by kidneys need adjustment
    - Underweight: may need lower doses
    """
    adjustments = []
    warnings = []
    risk_level = RiskLevel.low
    recommended = standard_dose

    drug_lower = drug_name.lower()

    # ── Age-based adjustments ──
    if age > 65:
        adjustments.append(f"Geriatric patient (age {age}): start with lowest effective dose")
        warnings.append("Elderly patients have reduced liver and kidney function. Drug clearance is slower.")

        if any(d in drug_lower for d in ["benzodiazepine", "diazepam", "lorazepam", "alprazolam"]):
            adjustments.append("Benzodiazepines: reduce dose by 50% in elderly — high fall risk")
            risk_level = RiskLevel.high

        if any(d in drug_lower for d in ["nsaid", "ibuprofen", "naproxen", "diclofenac"]):
            adjustments.append("NSAIDs: use lowest dose for shortest duration in elderly — high GI bleed risk")
            risk_level = RiskLevel.moderate

        if "metformin" in drug_lower:
            adjustments.append("Metformin: assess kidney function (eGFR) before continuing — contraindicated if eGFR < 30")

    if age < 12:
        adjustments.append(f"Pediatric patient (age {age}): use weight-based dosing (mg/kg)")
        warnings.append("Many adult drug doses are too high for children. Always verify pediatric dosing.")

        if any(d in drug_lower for d in ["aspirin"]):
            adjustments.append("ASPIRIN: Contraindicated in children under 16 — risk of Reye's syndrome")
            risk_level = RiskLevel.high

    if age < 2:
        warnings.append("Neonatal/infant dosing requires specialist consultation")
        risk_level = RiskLevel.high

    # ── Weight-based adjustments ──
    if weight_kg < 50 and age >= 12:
        adjustments.append(f"Underweight adult ({weight_kg}kg): dose may need reduction")
        if weight_kg < 40:
            risk_level = max(risk_level, RiskLevel.moderate, key=lambda x: ["low", "moderate", "high"].index(x.value))

    if weight_kg > 120:
        adjustments.append(f"Obese patient ({weight_kg}kg): some drugs may need higher loading doses")
        warnings.append("Drug distribution in obese patients may require specialist dose calculation")

    # ── Kidney function adjustments ──
    if kidney_function and kidney_function != "normal":
        renal_drugs = ["metformin", "lisinopril", "losartan", "digoxin", "atenolol",
                       "ciprofloxacin", "amoxicillin", "vancomycin", "lithium", "gabapentin"]

        if any(d in drug_lower for d in renal_drugs):
            if kidney_function == "severe":
                adjustments.append(f"Severe renal impairment: {drug_name} dose must be significantly reduced or drug avoided")
                risk_level = RiskLevel.high
                if "metformin" in drug_lower:
                    adjustments.append("METFORMIN: Contraindicated in severe renal impairment (eGFR < 30)")
                    warnings.append("Lactic acidosis risk is critically elevated")
            elif kidney_function == "moderate":
                adjustments.append(f"Moderate renal impairment: reduce {drug_name} dose by 25-50%")
                risk_level = RiskLevel.moderate
            elif kidney_function == "mild":
                adjustments.append(f"Mild renal impairment: monitor kidney function during {drug_name} therapy")
        else:
            adjustments.append(f"Renal impairment ({kidney_function}): monitor kidney function")

    # ── Default if no issues ──
    if not adjustments:
        adjustments.append("No specific dose adjustments indicated based on provided patient data")

    return DosageAdvice(
        standard_dose=standard_dose,
        recommended_dose=recommended,
        risk_level=risk_level,
        adjustments=adjustments,
        warnings=warnings
    )
