import json
from typing import Dict, Any

class MockArchitectRouter:
    def route(self, intent: str, concept: str) -> Dict[str, Any]:
        # Simulate successful generation if "REVISION" is in the concept (implying improvement)
        # Otherwise simulate a poor prompt that will fail audit.
        prompt = f"{concept}, shot on Arri Alexa 65, Zeiss Master Prime lenses."
        return {
            "status": "success",
            "payload": {"prompt": prompt}
        }

class MockKimiSemanticAudit:
    def audit(self, asset_content: str, brand_guidelines: str) -> Dict[str, Any]:
        # If the concept contains REVISION, simulate a passing score.
        if "[REVISION INSTRUCTION" in asset_content:
            return {
                "consistency_score": 98,
                "audit_results": {"tone_voice": {"status": "pass", "feedback": "Perfectly aligned."}},
                "critical_violations": [],
                "improvement_suggestions": []
            }
        else:
            # Simulate a failing score for the initial poor concept.
            return {
                "consistency_score": 40,
                "audit_results": {"tone_voice": {"status": "fail", "feedback": "Too informal."}},
                "critical_violations": ["Tone mismatch"],
                "improvement_suggestions": ["Use professional and minimalist language."]
            }

class SemanticRemediationLoop:
    def __init__(self, router=None, auditor=None, max_retries=3):
        self.router = router or MockArchitectRouter()
        self.auditor = auditor or MockKimiSemanticAudit()
        self.max_retries = max_retries

    def run_with_remediation(self, intent: str, concept: str, brand_guidelines: str) -> Dict[str, Any]:
        current_concept = concept
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            print(f"\n[ATTEMPT {attempts}] Generating via ArchitectRouter...")
            gen_res = self.router.route(intent, current_concept)
            if gen_res["status"] == "error": return {"status": "failed", "reason": "Gen error"}
            
            payload = gen_res["payload"]
            asset_content = payload["prompt"]

            print(f"[REMEDIATION LOOP] Auditing: {asset_content[:50]}...")
            audit_report = self.auditor.audit(asset_content, brand_guidelines)
            score = audit_report.get("consistency_score", 0)

            if score < 95:
                print(f"[REMEDIATION LOOP] Audit FAILED (Score: {score})")
                if attempts > self.max_retries: return {"status": "failed", "reason": "Max retries"}
                suggestions = audit_report.get("improvement_suggestions", ["Refine concept."])
                feedback = " ".join(suggestions)
                current_concept = f"{current_concept} [REVISION INSTRUCTION: {feedback}]"
            else:
                print(f"[REMEDIATION LOOP] Audit PASSED (Score: {score})")
                return {"status": "success", "attempts": attempts, "payload": payload}
        return {"status": "failed"}

if __name__ == "__main__":
    loop = SemanticRemediationLoop()
    guidelines = "Professional and minimalist."
    concept = "Hey guys! Check out this cheap watch!"
    print("STARTING MOCK TEST...")
    result = loop.run_with_remediation("high_fidelity_image", concept, guidelines)
    print("\nFINAL RESULT:\n", json.dumps(result, indent=2))
