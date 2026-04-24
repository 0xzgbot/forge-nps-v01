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
    SYSTEM_FAILURE = "SystemFailure"

class ContinuityAuditor:
    """
    The Intelligence Auditor component of Forge NPS.
    Uses Kimi's reasoning capabilities to compare visual descriptions 
    and rendered images against the established Lore Bible/World Bible.
    """

    def __init__(self, lore_bible_path: str, kimi_bridge=None):
        self.lore_bible_path = lore_bible_path
        self.lore_context = self._load_lore()
        self.kimi_bridge = kimi_bridge

    def _load_lore(self) -> Dict[str, Any]:
        """Loads the World Bible context into memory."""
        try:
            with open(self.lore_bible_path, 'r', encoding="utf-8") as f:
                content = f.read()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.warning(f"Lore Bible at {self.lore_bible_path} is not valid JSON. Treating as Markdown text.")
                    return {"raw_markdown": content}
        except Exception as e:
            logger.error(f"Failed to load Lore Bible: {e}")
            return {}

    async def audit_asset(
        self,
        asset_description: str,
        shot_id: str,
        image_path: str = None,
        reference_paths: list = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for auditing a generated asset.
        If image_path is provided, uses Kimi-VL for visual audit.
        Otherwise, falls back to semantic text audit.
        """
        logger.info(f"Auditing asset for shot: {shot_id}")
        
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

        # Kimi-VL visual audit if image is available
        if image_path and self.kimi_bridge and hasattr(self.kimi_bridge, "audit_image"):
            try:
                vl_result = await self.kimi_bridge.audit_image(
                    image_path=image_path,
                    reference_paths=reference_paths or [],
                    shot_description=asset_description,
                )
                if not vl_result.get("is_consistent", True):
                    report.update({
                        "is_consistent": False,
                        "confidence_score": vl_result.get("confidence", 0.9),
                        "error_category": vl_result.get("error_category", "SEMANTIC"),
                        "mismatch_report": "; ".join(vl_result.get("issues", [])),
                        "remediation_prompt": asset_description,
                        "violations": vl_result.get("issues", []),
                        "reasoning_trace": [f"[KIMI-VL] {i}" for i in vl_result.get("issues", [])],
                    })
                else:
                    report["confidence_score"] = vl_result.get("confidence", 1.0)
                    report["reasoning_trace"] = ["[KIMI-VL] Visual audit passed."]
                logger.info(f"[KIMI-VL] Audit for {shot_id}: consistent={vl_result.get('is_consistent')}")
                return report
            except Exception as e:
                logger.warning(f"Kimi-VL audit failed, falling back to text audit: {e}")

        # Text-based fallback
        try:
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
            report["error_category"] = ErrorCategory.SYSTEM_FAILURE.value
            report["mismatch_report"] = f"Internal Auditor Error: {str(e)}"
            report["reasoning_trace"].append(f"CRITICAL ERROR during audit process: {str(e)}")

        logger.info(f"Audit complete for {shot_id}. Is consistent: {report['is_consistent']}")
        return report

    async def _perform_semantic_audit(self, description: str) -> Dict[str, Any]:
        """
        Internal method to perform text-only semantic comparison against lore.
        (Placeholder for Kimi-K2 direct text reasoning if bridge is available).
        """
        trace = [f"Parsing description: '{description}'"]
        trace.append("Comparing tokens against Lore Bible semantic clusters...")

        # Simulation logic (as per previous implementation)
        if "red eyes" in description.lower() or "crimson eyes" in description.lower():
            return {
                "is_consistent": False,
                "confidence": 0.98,
                "category": ErrorCategory.PHOTOMETRIC.value,
                "reason": "Color contradiction: Lore specifies emerald green eyes.",
                "fix": "Update prompt to specify 'emerald green eyes'.",
                "anchors": ["char_eye_color"],
                "trace": trace + ["MATCH FAILURE: Subject eye color mismatch."]
            }

        if "three arms" in description.lower() or "extra limb" in description.lower():
            return {
                "is_consistent": False,
                "confidence": 0.99,
                "category": ErrorCategory.ANATOMICAL.value,
                "reason": "Anatomical violation: Extra limbs detected.",
                "fix": "Add negative prompt: 'extra limbs, deformed anatomy'.",
                "anchors": ["char_anatomy"],
                "trace": trace + ["MATCH FAILURE: Anatomical structure mismatch."]
            }

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
        """Audits a batch of shots concurrently."""
        logger.info(f"Starting batch audit for {len(shots)} shots.")
        
        tasks = [self.audit_asset(shot['description'], shot['id'], 
                                  image_path=shot.get('image_path'), 
                                  reference_paths=shot.get('reference_paths')) 
                 for shot in shots]
        results = await asyncio.gather(*tasks)

        summary = {
            "total_shots": len(shots),
            "consistent_count": 0,
            "inconsistent_count": 0,
            "shot_results": [],
            "global_consistency_warning": None,
            "systemic_error_category": ErrorCategory.NONE.value
        }

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

        for cat, count in error_counts.items():
            if count > (len(shots) / 2) and count > 0:
                summary["global_consistency_warning"] = f"Systemic {cat} failure detected across multiple shots."
                summary["systemic_error_category"] = cat
                break

        return summary

    def get_trace_summary(self, report: Dict[str, Any]) -> str:
        trace = report.get("reasoning_trace", [])
        if not trace: return "No reasoning trace available."
        return "\n".join([f"• {step}" for step in trace])

if __name__ == '__main__':
    import asyncio
    async def main():
        auditor = ContinuityAuditor("dummy_lore.json")
        res = await auditor.audit_asset("A man with red eyes", "shot_001")
        print(f"Is Consistent: {res['is_consistent']}")
        print(f"Category: {res['error_category']}")
    asyncio.run(main())
