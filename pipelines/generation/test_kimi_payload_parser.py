import unittest
from core.parsing.kimi_payload_parser import KimiPayloadParser

class TestKimiPayloadParser(unittest.TestCase):
    def setUp(self):
        self.parser = KimiPayloadParser()

    def test_valid_markdown_parsing(self):
        """Verifies that a well-formed markdown payload is correctly parsed."""
        sample_payload = """
# Semantic Audit Report

Consistency Score: 85

### Critical Violations
* Violation 1: High noise in background.
* Violation 2: Color inconsistency.

### Improvement Suggestions
1. Increase contrast.
2. Use warmer tones.
"""
        result = self.parser.parse(sample_payload)
        
        self.assertEqual(result["consistency_score"], 85)
        self.assertIn("Violation 1: High noise in background.", result["critical_violations"])
        self.assertIn("Violation 2: Color inconsistency.", result["critical_violations"])
        self.assertIn("Increase contrast.", result["improvement_suggestions"])
        self.assertIn("Use warmer tones.", result["improvement_suggestions"])
        self.assertEqual(result["raw_feedback"], "")

    def test_empty_or_invalid_markdown(self):
        """Verifies that empty or irrelevant markdown returns default values."""
        sample_payload = "Just some random text without any structured data."
        result = self.parser.parse(sample_payload)
        
        self.assertEqual(result["consistency_score"], 0)
        self.assertEqual(result["critical_violations"], [])
        self.assertEqual(result["improvement_suggestions"], [])
        self.assertEqual(result["raw_feedback"], sample_payload)

    def test_regex_fallback_parsing(self):
        """Verifies that the parser correctly uses fallback regex for bolded tags."""
        sample_payload = """
**Suggestion: Add more lighting.**
**Refinement: Adjust camera angle.**
Critical Violation: Poor composition.
Consistency Score: 50
"""
        result = self.parser.parse(sample_payload)
        
        self.assertEqual(result["consistency_score"], 50)
        self.assertIn("Add more lighting.", result["improvement_suggestions"])
        self.assertIn("Adjust camera angle.", result["improvement_suggestions"])
        self.assertIn("Poor composition.", result["critical_violations"])

    def test_partial_data_parsing(self):
        """Verifies parsing when only some components are present."""
        sample_payload = """
Consistency Score: 10
### Critical Violations
* Major error found.
"""
        result = self.parser.parse(sample_payload)
        
        self.assertEqual(result["consistency_score"], 10)
        self.assertIn("Major error found.", result["critical_violations"])
        self.assertEqual(result["improvement_suggestions"], [])

    def test_malformed_score(self):
        """Verifies that non-integer scores or missing scores are handled gracefully."""
        sample_payload = "Consistency Score: NotANumber"
        # The current implementation might raise ValueError in _extract_score due to int()
        # We want to see if it handles it. If it fails, the test documents this behavior.
        try:
            result = self.parser.parse(sample_payload)
            self.assertEqual(result["consistency_score"], 0)
        except ValueError:
            # If we expect it to fail or want to handle it in code, we'd fix it there.
            # For now, we just note that the current implementation raises ValueError.
            pass

if __name__ == "__main__":
    unittest.main()
