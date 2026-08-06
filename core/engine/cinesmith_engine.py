import asyncio
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in PYTHONPATH for package imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Import Cinesmith Components
try:
    from core.routing.architect_router import ArchitectRouter
    from core.dispatch.dispatcher import ComfyDispatcher as Dispatcher
    from core.feedback.remediation_loop import RemediationLoop as SemanticRemediationLoop
except ImportError as e:
    print(f"[CinesmithEngine] Import warning: {e}. Some features may be unavailable.")
    ArchitectRouter = None
    Dispatcher = None
    SemanticRemediationLoop = None

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [CINESMITH-ENGINE] - %(levelname)s - %(message)s')
logger = logging.getLogger("CinesmithEngine")

class CinesmithEngine:
    """
    DEPRECATED — superseded by CinesmithOrchestrator.

    Use core.orchestrator.cinesmith_orchestrator.CinesmithOrchestrator instead.
    This legacy class is kept for backward-compatibility with older scripts
    and will be removed in a future version.
    """
    def __init__(self):
        warnings.warn(
            "CinesmithEngine is deprecated. Use CinesmithOrchestrator "
            "(core.orchestrator.cinesmith_orchestrator) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if ArchitectRouter is None or Dispatcher is None:
            raise ImportError("CinesmithEngine dependencies unavailable. Use CinesmithOrchestrator instead.")
        self.router = ArchitectRouter()
        self.dispatcher = Dispatcher(hosts=[])
        self.remediation_loop = None
        logger.info("CinesmithEngine initialized (legacy mode).")

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
    engine = CinesmithEngine()
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
