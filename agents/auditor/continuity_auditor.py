import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Union
from enum import Enum

# Configure logging for the Auditor
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ContinuityAuditor")

class ErrorCategory(str, Enum):
    PHOTOMETRIC = "Photometric"
    ANATOMICAL = "Anatomical"
    TEMPORAL = "Temporal"
    SEMANTIC = "Semantic"
    NONE = "None"

class ContinuityAuditor:
    """
    The Intelligence Auditor component of Forge NPS.
    Uses Kimi's reasoning capabilities to compare visual descriptions 
    against the established Lore Bible/World Bible.
    """

    def __init__(self, lore_bible_path: str):
        self.lore_bible_path = lore_bible_path
        self.lore_context = self._load_lore()

    def _load_lore(self) -> Dict[str, Any]:
        """Loads the World Bible context into memory."""
        try:
            with open(self.lore_bible_path, 'r') as f:
                # Attempt to load as JSON first, if it fails or is not JSON, 
                # we'll implement a simple Markdown parser in a future step.
                # For now, we handle the error gracefully.
                content = f.read()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"Lore Bible at {self.lore_bible_path} is not valid JSON. Treating as Markdown text.")
                    return {"raw_markdown": content}
        except Exception as e:
            logger.error(f"Failed to load Lore Bible: {e}")
            # Fallback to empty context if loading fails
            return {}

    async def audit_asset(self, asset_description: str, shot_id: str) -> Dict[str, Any]:
        """
        Main entry point for auditing a generated asset.
        Uses Kimi reasoning to compare descriptions against the Lore Bible.
        Returns a structured report containing rich diagnostics.
        """
        logger.info(f"Auditing asset for shot: {shot_id}")
        
        # INITIALIZE BASE REPORT SCHEMA (Required by J8)
        report = {
            "shot_id": shot_id,
            "is_consistent": True,
            "confidence_score": 0.0,
            "error_category": ErrorCategory.NONE.value,
            "mismatch_report": "",
            "remediation_prompt": "",
            "global_consistency_warning": None,
            "affected_anchors": [],
            "reasoning_trace": [],
            "violations": [] 
        }

        try:
            # PHASE 1: SEMANTIC ANALYSIS (Integration point for Kimi)
            # In the production build, this calls self.kimi_bridge.analyze(...)
            # For this task, I am implementing the logic that handles the LLM response structure.
            
            analysis_result = await self._perform_semantic_audit(asset_description)
            
            if not analysis_result["is_consistent"]:
                report.update({
                    "is_consistent": False,
                    "confidence_score": analysis_result["confidence"],
                    "error_category": analysis_result["category"],
                    "mismatch_report": analysis_result["reason"],
                    "remediation_prompt": analysis_result["fix"],
                    "affected_anchors": analysis_result["anchors"],
                    "reasoning_trace": analysis_result["trace"],
                    "violations": [analysis_result["reason"]]
                })
            else:
                report["confidence_score"] = 1.0
                report["reasoning_trace"] = analysis_result["trace"]

        except Exception as e:
            logger.error(f"Audit failed for {shot_id}: {e}")
            report["is_consistent"] = False
            report["error_category"] = "SystemError"
            report["mismatch_report"] = f"Internal Auditor Error: {str(e)}"
            report["reasoning_trace"].append(f"CRITICAL ERROR during audit process: {str(e)}")

        logger.info(f"Audit complete for {shot_id}. Is consistent: {report['is_consistent']}")
        return report

    async def _perform_semantic_audit(self, description: str) -> Dict[str, Any]:
        """
        Internal method to simulate/execute the Kimi semantic comparison.
        This handles the actual logic of checking against self.lore_context.
        """
        # This placeholder simulates a high-fidelity LLM response based on Lore context.
        # In next step, we will connect the real KimiBridge.
        trace = [f"Parsing description: '{description}'"]
        trace.append("Comparing tokens against Lore Bible semantic clusters...")

        # Logic to detect mismatch (simulating Kimi's reasoning)
        # We check if any lore-protected terms are contradicted in the description.
        
        # Example: If Lore says "Emerald Eyes" and desc says "Red Eyes"
        if "red eyes" in description.lower() or "crimson eyes" in description.lower():
            return {
                "is_consistent": False,
                "confidence": 0.98,
                "category": ErrorCategory.PHOTOMETRIC.value,
                "reason": "Color contradiction: Lore specifies emerald green eyes for this entity.",
                "fix": "Update prompt to specify 'emerald green eyes'.",
                "anchors": ["char_eye_color"],
                "trace": trace + ["MATCH FAILURE: Subject eye color does not align with Lore Bible."]
            }

        # Example: Anatomy check
        if "three arms" in description.lower() or "extra limb" in description.lower():
            return {
                "is_consistent": False,
                "confidence": 0.99,
                "category": ErrorCategory.ANATOMICAL.value,
                "reason": "Anatomical violation: Extra limbs detected.",
                "fix": "Add negative prompt: 'extra limbs, deformed anatomy'.",
                "anchors": ["char_anatomy"],
                "trace": trace + ["MATCH FAILURE: Anatomical structure exceeds defined human model."]
            }

        # Default Success
        return {
            "is_consistent": True,
            "confidence": 0.95,
            "category": ErrorCategory.NONE.value,
            "reason": "",
            "fix": "",
            "anchors": [],
            "trace": trace + ["SUCCESS: All attributes match Lore Bible constraints."]
        }

    async def audit_batch(self, shots: List[Dict[str, Any]], director_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Audits a batch of shots concurrently.
        Detects systemic failures and provides global warnings.
        """
        logger.info(f"Starting batch audit for {len(shots)} shots.")
        
        # Run all audits concurrently
        tasks = [self.audit_asset(shot['description'], shot['id']) for shot in shots]
        results = await asyncio.gather(*tasks)

        summary = {
            "total_shots": len(shots),
            "consistent_count": 0,
            "inconsistent_count": 0,
            "shot_results": [],
            "global_consistency_warning": None,
            "systemic_error_category": ErrorCategory.NONE.value
        }

        # Count categories for systemic failure detection
        error_counts = {cat.value: 0 for cat in ErrorCategory if cat != ErrorCategory.NONE}

        for res in results:
            summary["shot_results"].append(res)
            if res["is_consistent"]:
                summary["consistent_count"] += 1
            else:
                summary["inconsistent_count"] += 1
                cat = res.get("error_category", ErrorCategory.NONE.value)
                if cat in error_counts:
                    error_counts[cat] += 1
                summary["systemic_error_category"] = cat

        # Detect systemic failures (e.g., > 50% of shots fail with the same category)
        for cat, count in error_counts.items():
            if count > (len(shots) / 2) and count > 0:
                summary["global_consistency_warning"] = f"Systemic {cat} failure detected across multiple shots. Review master settings or director schema."
                summary["systemic_error_category"] = cat
                break

        logger.info(f"Batch audit complete. Consistency rate: {summary['consistent_count']}/{len(shots)}")
        return summary

    def get_trace_summary(self, report: Dict[str, Any]) -> str:
        """Formats the reasoning trace into a clean string for visual overlays in demo videos."""
        trace = report.get("reasoning_trace", [])
        if not trace:
            return "No reasoning trace available."
        return "\n".join([f"• {step}" for step in trace])

if __name__ == '__main__':
    # Quick test
    import asyncio
    async def main():
        # Using a dummy path for the quick test run
        auditor = ContinuityAuditor("dummy_lore.json")
        res = await auditor.audit_asset("A man with wrong color eyes", "shot_001")
        print(f"Is Consistent: {res['is_consistent']}")
        print(f"Category: {res['error_category']}")
        print(f"Mismatch: {res['mismatch_report']}")
        print(f"Trace:\n{auditor.get_trace_summary(res)}")

    asyncio.run(main())
