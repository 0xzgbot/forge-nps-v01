import asyncio
import json
import logging
import sys
import os
from typing import List, Dict, Any

# Ensure project root is in PYTHONPATH for package imports
sys.path.append("~/Desktop/forge_nps_v01")

# Import Forge Components
try:
    from core.routing.architect_router import ArchitectRouter
    from core.dispatch.dispatcher import ComfyDispatcher as Dispatcher
    from core.feedback.remediation_loop import RemediationLoop as SemanticRemediationLoop
except ImportError as e:
    print(f"[ForgeEngine] Import warning: {e}. Some features may be unavailable.")
    ArchitectRouter = None
    Dispatcher = None
    SemanticRemediationLoop = None

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [FORGE-ENGINE] - %(levelname)s - %(message)s')
logger = logging.getLogger("ForgeEngine")

class ForgeEngine:
    """
    Legacy entry point — superseded by ForgeOrchestrator.
    Kept for backward-compatibility with older scripts.
    """
    def __init__(self):
        if ArchitectRouter is None or Dispatcher is None:
            raise ImportError("ForgeEngine dependencies unavailable. Use ForgeOrchestrator instead.")
        self.router = ArchitectRouter()
        self.dispatcher = Dispatcher(hosts=[])
        self.remediation_loop = None
        logger.info("ForgeEngine initialized (legacy mode).")

    async def run_production_batch(self, concepts: List[Dict[str, str]]):
        """
        Processes a batch of concepts through the complete production pipeline.
        'concepts' format: [{"intent": "cinematic_video", "concept": "A dragon flying..."}]
        """
        logger.info(f"Starting production batch for {len(concepts)} items.")
        
        # Pre-flight connectivity check
        if not await self.dispatcher.check_connectivity():
            logger.error("Aborting production batch: No hardware hosts are reachable.")
            return [{"status": "failed", "reason": "hardware_unreachable"}] * len(concepts)

        tasks = [self.process_single_item(c) for c in concepts]
        results = await asyncio.gather(*tasks)
        logger.info("Batch production complete.")
        return results

    async def process_single_item(self, item: Dict[str, str]) -> Dict[str, Any]:
        intent = item.get("intent", "high_fidelity_image")
        concept = item.get("concept", "")
        
        logger.info(f"Processing Item: [Intent: {intent}] | [Concept: {concept[:50]}...]")

        # 1. Routing & Payload Synthesis
        routing_result = self.router.route(intent, concept)
        if routing_result["status"] != "success":
            logger.error(f"Routing Failed: {routing_result['message']}")
            return {"concept": concept, "status": "failed", "reason": "routing_error"}

        payload = routing_result["payload"]
        kernel_id = routing_result["kernel_id"]

        # 2. Dispatch & Generation (wrapped in Remediation Loop)
        generation_result = await self.remediation_loop.execute_with_retry(
            dispatcher=self.dispatcher,
            payload=payload,
            original_concept=concept,
            kernel_id=kernel_id
        )

        if generation_result["status"] == "success":
            logger.info(f"Successfully produced asset via {kernel_id}")
            return {"concept": concept, "status": "success", "payload": generation_result}
        else:
            logger.error(f"Production failed after remediation attempts: {generation_result['reason']}")
            return {"concept": concept, "status": "failed", "reason": generation_result['reason']}

async def main():
    # Simulation Test Batch
    engine = ForgeEngine()
    test_batch = [
        {"intent": "high_fidelity_image", "concept": "A cyberpunk street at night with neon reflections"},
        {"intent": "cinematic_video", "concept": "Slow drone shot of a mountain range during sunset"},
        {"intent": "fast_preview_image", "concept": "Sketch of a futuristic car"}
    ]
    
    results = await engine.run_production_batch(test_batch)
    print("\n--- FINAL PRODUCTION REPORT ---")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
