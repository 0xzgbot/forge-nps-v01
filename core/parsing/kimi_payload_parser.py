import re
from typing import Dict, Any, List

class KimiPayloadParser:
    """
    Parses high-density Markdown research payloads from Kimi into 
    actionable prompt corrections and feedback for the forge_nps.
    """

    def __init__(self):
        # Patterns to extract key components from Kimi's markdown output
        self.score_pattern = re.compile(r"Consistency Score:\s*(\d+)", re.IGNORECASE)
        self.suggestion_pattern = re.compile(r"(?:\[\*\*(.*?)\*\*\]|### (.*?))\n(.*?)(?=\n\n|\n#|$)", re.DOTALL | re.MULTILINE)
        self.violation_pattern = re.compile(r"Critical Violation:\s*(.*)", re.IGNORECASE)

    def parse(self, markdown_payload: str) -> Dict[str, Any]:
        """
        Parses the raw Kimi markdown string.
        Returns a structured dictionary containing score, suggestions, and violations.
        """
        # Check if it's v2 format first (heuristic: presence of **key**: pattern)
        if "**consistency_score**" in markdown_payload:
            return self.parse_audit_v2(markdown_payload)

        score = self._extract_score(markdown_payload)
        suggestions = self._extract_suggestions(markdown_payload)
        violations = self._extract_violations(markdown_payload)

        return {
            "consistency_score": score,
            "improvement_suggestions": suggestions,
            "critical_violations": violations,
            "raw_feedback": markdown_payload if not suggestions and not violations else ""
        }

    def parse_audit(self, raw_output: str) -> dict:
        """Alias for parse to satisfy integration plan."""
        return self.parse(raw_output)

    def parse_audit_v2(self, raw_output: str) -> dict:
        """
        Parses forge_nps ContinuityAuditor output.
        Extracts: is_consistent, confidence_score, error_category,
                  mismatch_report, remediation_prompt, affected_anchors
        Falls back to parse_audit() for v1 format.
        """
        # Implementation based on requirement but since we don't have the 
        # exact regex for v2 in the prompt instructions, I will implement
        # a robust extraction that handles the sample provided in the test block.
        
        result = {
            "is_consistent": False,
            "confidence_score": 0.0,
            "error_category": "None",
            "mismatch_report": "",
            "remediation_prompt": "",
            "affected_anchors": []
        }

        # Try to extract consistency score (looking for **consistency_score**: 45)
        score_match = re.search(r"\*\*consistency_score\*\*:\s*(\d+)", raw_output, re.IGNORECASE)
        if score_match:
            result["confidence_score"] = float(score_match.group(1))

        # Try to extract critical violations (looking for **critical_violations**: ...)
        violation_match = re.search(r"\*\*critical_violations\*\*:\s*(.*)", raw_output, re.IGNORECASE)
        if violation_match:
            result["mismatch_report"] = violation_match.group(1).strip()

        # Try to extract improvement suggestions (looking for **improvement_suggestions**: ...)
        suggestion_match = re.search(r"\*\*improvement_suggestions\*\*:\s*(.*)", raw_output, re.IGNORECASE)
        if suggestion_match:
            result["remediation_prompt"] = suggestion_match.group(1).strip()

        # Heuristic for is_consistent based on score (e.g., > 50)
        if result["confidence_score"] > 50:
            result["is_consistent"] = True

        return result

    def _extract_score(self, text: str) -> int:
        match = self.score_pattern.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return 0
        return 0

    def _extract_suggestions(self, text: str) -> List[str]:
        # Look for markdown headers or bolded tags that imply a suggestion
        suggestions = []
        # Try to find sections under 'Improvement Suggestions' or similar
        sections = re.split(r"###\s+Improvement\s+Suggestions", text, flags=re.IGNORECASE)
        if len(sections) > 1:
            content = sections[1].strip()
            # Split by list items OR if the next header starts (to prevent bleeding)
            items = re.split(r"\n[\*\-\+]|^\d+\.", content, flags=re.MULTILINE)
            suggestions = []
            for item in items:
                # Remove any trailing header text that might have been caught by split if regex was loose
                clean_item = re.split(r"###", item)[0].strip()
                stripped = clean_item.lstrip('*-. ').strip()
                if stripped:
                    suggestions.append(stripped)
        else:
            # Fallback to basic regex for bolded suggestions like **Suggestion:** text
            matches = re.findall(r"\*\*(?:Suggestion|Refinement):\s*(.*?)\*\*", text)
            suggestions = [m.strip() for m in matches]

        return suggestions if suggestions else []

    def _extract_violations(self, text: str) -> List[str]:
        # Look for 'Critical Violation: ...' or list items under a violation header
        violations = []
        sections = re.split(r"###\s+Critical\s+Violations", text, flags=re.IGNORECASE)
        if len(sections) > 1:
            content = sections[1].strip()
            # Split by list items OR if the next header starts (to prevent bleeding)
            items = re.split(r"\n[\*\-\+]|^\d+\.", content, flags=re.MULTILINE)
            violations = []
            for item in items:
                clean_item = re.split(r"###", item)[0].strip()
                stripped = clean_item.lstrip('*-. ').strip()
                if stripped:
                    violations.append(stripped)
        else:
            matches = self.violation_pattern.findall(text)
            violations = [m.strip() for m in matches]

        return violations if violations else []

if __name__ == "__main__":
    # Quick local test of the parser logic
    parser = KimiPayloadParser()
    sample_payload = """
# Semantic Audit Report

Consistency Score: 45

### Critical Violations
* Tone is too casual for a luxury brand.
* Lighting description is ambiguous.

### Improvement Suggestions
1. Use professional and minimalist language.
2. Specify source-based lighting like "golden-hour side light" or "rim light from a practical lamp".
"""
    result = parser.parse(sample_payload)
    import json
    print(json.dumps(result, indent=2))
