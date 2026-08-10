from pydantic import BaseModel

class MockSchema(BaseModel):
    is_consistent: bool
    confidence_score: float
    error_category: str = "None"
    mismatch_report: str = ""
    remediation_prompt: str = ""
    affected_anchors: list[str] = []

import pytest

@pytest.mark.asyncio
async def test_fallback():
    # Testing the parser directly first as planned by the requirement's logic check
    non_json_markdown = """
**consistency_score**: 45
**critical_violations**: Color bleeding in neon environment
**improvement_suggestions**: Add strict color grading directive
"""

    print("Testing Non-JSON Markdown Fallback parsing...")
    from core.parsing.kimi_payload_parser import KimiPayloadParser
    parser = KimiPayloadParser()
    result = parser.parse_audit_v2(non_json_markdown)
    print(f"Parsed result: {result}")
    assert result["confidence_score"] == 45.0
    assert "Color bleeding" in result["mismatch_report"]
    print("Parser logic check PASS")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_fallback())
