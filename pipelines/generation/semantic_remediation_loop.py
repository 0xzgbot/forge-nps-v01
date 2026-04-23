import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable

try:
    from .kimi_payload_parser import KimiPayloadParser
except ImportError:
    try:
        from kimi_payload_parser import KimiPayloadParser
    except ImportError:
        class KimiPayloadParser:
            def parse(self, text): return {"consistency_score": 0, "improvement_suggestions": []}

logger = logging.getLogger("RemediationLoop")

class SemanticRemediationLoop:
    """
    Handles the intelligent feedback loop for content generation.
    Uses Kimi LLM to audit assets and triggers retries by re-routing 
    refined concepts through the ArchitectRouter to ensure schema compliance.
    """
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.parser = KimiPayloadParser()

    async def execute_with_retry(
        self, 
        dispatcher: Any, 
        original_concept: str, 
        kernel_id: str,
        reroute_callback: Callable[[str, str], Awaitable[Dict[str, Any]]],
        auditor_callback: Any = None
    ) -> Dict[str, Any]:
        """
        The core loop: Dispatch -> Audit -> (If fail) RE-ROUTE CONCEPT $\rightarrow$ Re-Dispatch.
        
        Args:
            dispatcher: The object responsible for sending payloads to ComfyUI.
            original_concept: The high-level human intent.
            kernel_id: The target model identifier (e.g., 'flux2', 'wan21').
            reroute_callback: A function that takes (new_concept, kernel_id) and 
                             returns a brand new, schema-compliant payload via ArchitectRouter.
            auditor_callback: An object with an .audit(prompt, guidelines) method returning Kimi feedback.
        """
        attempt = 0
        current_concept = original_concept
        # Initial generation
        current_payload = await reroute_callback(current_concept, kernel_id)

        while attempt <= self.max_retries:
            logger.info(f"Generation attempt {attempt + 1} for concept: '{current_concept[:30]}...'")
            
            # Step 1: Dispatch to ComfyUI via the dispatcher
            dispatch_result = await dispatcher.dispatch(current_payload)

            if dispatch_result["status"] != "success":
                logger.error(f"Attempt {attempt+1} failed at Dispatch stage: {dispatch_result.get('message')}")
                return {"status": "error", "reason": f"dispatch_failed_{dispatch_result.get('message')}"}

            # Step 2: Semantic Audit
            if auditor_callback:
                audit_response = await auditor_callback.audit(current_payload["prompt"], "Brand Guidelines")
            else:
                # Fallback for testing
                audit_response = self._perform_mock_audit(attempt)

            # Parse Kimi's feedback (supports both raw MD and mock dicts)
            if isinstance(audit_response, str):
                audit_data = self.parser.parse(audit_response)
                score = audit_data.get("consistency_score", 0)
                suggestions = audit_data.get("improvement_suggestions", [])
            else:
                score = audit_response.get("consistency_score", 0)
                suggestions = audit_response.get("improvement_suggestions", [])

            if score >= 90:
                logger.info(f"Audit PASSED (Score: {score})")
                return {
                    "status": "success",
                    "score": score,
                    "payload": dispatch_result
                }
            else:
                logger.warning(f"Audit FAILED (Score: {score}). Initiating remediation...")
                attempt += 1
                if attempt > self.max_retries:
                    break

                # Step 3: RE-ROUTING (The Fix)
                # Instead of appending to a string, we refine the concept and call the router again.
                feedback_str = "; ".join(suggestions) if suggestions else "enhance visual fidelity"
                current_concept = f"{original_concept} | Refinement: {feedback_str}"
                
                logger.info(f"Re-routing concept through ArchitectRouter: '{current_concept[:40]}...'")
                # We call the reroute_callback to get a brand new, valid JSON payload from the Router
                current_payload = await reroute_callback(current_concept, kernel_id)

        return {"status": "error", "reason": "max_retries_exceeded"}

    def _perform_mock_audit(self, attempt: int) -> Dict[str, Any]:
        if attempt == 0: return {"consistency_score": 45, "improvement_suggestions": ["Make it more cinematic"]}
        return {"consistency_score": 98}

if __name__ == "__main__":
    import asyncio
    import logging

    async def test():
        logging.basicConfig(level=logging.INFO)
        loop = SemanticRemediationLoop()

        class MockDispatcher:
            async def dispatch(self, payload): 
                return {"status": "success", "payload": payload}

        class MockAuditor:
            async def audit(self, content, guidelines):
                # Simulate a failure on the first attempt
                if "Refinement" not in content:
                    return "# Semantic Audit Report\nConsistency Score: 40\n### Improvement Suggestions\n* Make it more cinematic."
                return "# Semantic Audit Report\nConsistency Score: 95\n### Improvement Suggestions\n* None."

        class MockRouter:
            async def route(self, concept, kernel_id):
                # Mimics ArchitectRouter returning a valid payload
                return {"prompt": concept, "kernel": kernel_id, "params": {"strength": 1.0}}

        router = MockRouter()
        dispatcher = MockDispatcher()
        auditor = MockAuditor()

        print("--- RUNNING TEST: INTENT RE-ROUTING ---")
        res = await loop.execute_with_retry(
            dispatcher, 
            "test concept", 
            "flux2", 
            reroute_callback=router.route, 
            auditor_callback=auditor
        )
        print(f"Final Result: {res}")

    asyncio.run(test())
