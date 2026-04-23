import re
from typing import Dict, Any, List

class KimiPayloadParser:
    """
    Parses high-density Markdown research payloads from Kimi into 
    actionable prompt corrections and feedback for the Architect Router.
    """

    def __init__(self):
        # Patterns to extract key components from Kimi's markdown output
        self.score_pattern = re.compile(r"Consistency Score:\s*(\d+)", re.IGNORECASE)
        self.violation_pattern = re.compile(r"Critical Violation:\s*(.*)", re.IGNORECASE)

    def parse(self, markdown_payload: str) -> Dict[str, Any]:
        """
        Parses the raw Kimi markdown string.
        Returns a structured dictionary containing score, suggestions, and violations.
        """
        score = self._extract_score(markdown_payload)
        suggestions = self._extract_suggestions(markdown_payload)
        violations = self._extract_violations(markdown_payload)

        return {
            "consistency_score": score,
            "improvement_suggestions": suggestions,
            "critical_violations": violations,
            "raw_feedback": markdown_payload if not suggestions and not violations else ""
        }

    def _extract_score(self, text: str) -> int:
        match = self.score_pattern.search(text)
        return int(match.group(1)) if match else 0

    def _extract_suggestions(self, text: str) -> List[str]:
        suggestions = []
        # Use regex to find the header and everything until the next header or end of string
        pattern = re.compile(r"###\s+Improvement\s+Suggestions\s*(.*?)(?=\n#|\n###|$)", re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            # Split by list markers (*, -, +) or numbered lists (1., 2.)
            items = re.split(r"\n[\*\-\+]|\n\d+\.", content)
            suggestions = [item.strip("* -+").strip() for item in items if item.strip()]
        
        # Fallback to bolded suggestions
        if not suggestions:
            matches = re.findall(r"\*\*(?:Suggestion|Refinement):\s*(.*?)\*\*", text)
            suggestions = [m.strip() for m in matches]

        return suggestions if suggestions else []

    def _extract_violations(self, text: str) -> List[str]:
        violations = []
        pattern = re.compile(r"###\s+Critical\s+Violations\s*(.*?)(?=\n#|\n###|$)", re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            items = re.split(r"\n[\*\-\+]|\n\d+\.", content)
            violations = [item.strip("* -+").strip() for item in items if item.strip()]

        if not violations:
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
2. Specify cinematic lighting like "Golden hour" or "Rim lighting".
"""
    result = parser.parse(sample_payload)
    import json
    print(json.dumps(result, indent=2))
