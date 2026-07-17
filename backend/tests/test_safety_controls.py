"""Safety-critical unit tests runnable with the Python standard library."""
import sys
from pathlib import Path
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from models.schemas import ImageVerifyRequest
from services.confidence import compute_confidence, determine_verdict
from services.gtin import validate_gtin


class VerificationSafetyTests(unittest.TestCase):
    def test_record_match_cannot_become_authentic_without_serial_check(self):
        self.assertEqual(determine_verdict(99, serial_verification=None, no_active_recall=True), "unknown")

    def test_authoritative_serial_check_controls_final_claim(self):
        self.assertEqual(determine_verdict(99, serial_verification=True, no_active_recall=True), "authentic")
        self.assertEqual(determine_verdict(99, serial_verification=False, no_active_recall=True), "counterfeit")

    def test_active_recall_is_never_authentic(self):
        self.assertEqual(determine_verdict(99, serial_verification=True, no_active_recall=False), "suspicious")

    def test_invalid_gtin_is_rejected(self):
        self.assertFalse(validate_gtin("12345678901234")["valid"])

    def test_missing_recall_coverage_is_not_reported_as_clear(self):
        confidence, evidence = compute_confidence(False, True, None)
        recall = next(item for item in evidence if item.check == "recall_check")
        self.assertEqual(confidence, 0.0)
        self.assertEqual(recall.status, "warn")

    def test_malformed_image_is_rejected_before_processing(self):
        with self.assertRaises(ValueError):
            ImageVerifyRequest(image="not valid base64!!!")


if __name__ == "__main__":
    unittest.main()
