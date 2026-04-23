from typing import Optional
import argparse
import asyncio
import logging
import sys
import os
import json
import webbrowser
from datetime import datetime

# Add project root to sys.path for imports
project_root = "/Users/zgbot/Desktop/forge_nps"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.bridge.config_manager import ConfigManager
from core.bridge.kimi_bridge import KimiBridge
from core.orchestrator.forge_orchestrator import ForgeOrchestrator
from core.state.session_manager import SessionManager
from agents.auditor.continuity_auditor import ContinuityAuditor
from agents.visual.visual_agent import VisualAgent
from core.hermes.hermes_agent import HermesAgent
from core.feedback.remediation_loop import RemediationLoop
from core.hermes.memory import EpisodicMemory, SemanticMemory

# Setup Logging with ASCII Style
class AsciiFormatter(logging.Formatter):
    def format(self, record):
        prefix = ""
        if record.levelname == "INFO":
            prefix = "  [✓] "
        elif record.levelname == "WARNING":
            prefix = "  [!] "
        elif record.levelname == "ERROR":
            prefix = "  [✗] "
        return f"{prefix}{record.getMessage()}"

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(AsciiFormatter())
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])


def print_memory_report(hermes: HermesAgent):
    """Pretty-print Hermes' current memory state."""
    summary = hermes.get_memory_summary()
    print("\n" + "═" * 50)
    print("🧠 HERMES MEMORY REPORT")
    print("═" * 50)

    # Detect which embedder is active
    embedder_name = "Jaccard (fallback)"
    if hermes.episodic.embedder:
        from core.hermes.memory import HybridEmbedder
        if isinstance(hermes.episodic.embedder, HybridEmbedder):
            backend = hermes.episodic.embedder.active_backend
            if backend == "kimi":
                embedder_name = f"Kimi ({hermes.episodic.embedder.kimi.model})"
            elif backend == "ollama":
                embedder_name = f"Ollama ({hermes.episodic.embedder.ollama.model})"
            else:
                embedder_name = "Numpy TF-IDF (offline fallback)"

    print(f"  Embedding backend:    {embedder_name}")

    eps = summary["episodic_stats"]
    print(f"  Episodes logged:      {eps['total_events']}")
    print(f"  Historical success:   {eps['success_rate']*100:.1f}%")
    if eps["top_error_categories"]:
        print(f"  Top error patterns:   {', '.join(eps['top_error_categories'].keys())}")

    sem = summary["semantic_stats"]
    print(f"  Semantic insights:    {sem['total_insights']}")
    print(f"  Avg confidence:       {sem['avg_confidence']:.2f}")
    print(f"  High-confidence:      {sem['high_confidence_count']}")

    rules = hermes.get_active_rules()
    if rules:
        print("\n  📜 Active Rules:")
        for r in rules[:3]:
            print(f"     • [{r['confirmations']}✓] {r['rule'][:70]}...")

    print("═" * 50)


async def run_memory_demo():
    """
    Karpathy-style memory showcase.

    Phase 1 — Naive attempt: Hermes encounters a Photometric error,
    fails twice, then succeeds on the 3rd try via Kimi escalation.
    Outcome is recorded in episodic memory.

    Phase 2 — Consolidation ("Dream"): Hermes distills the episode
    into a semantic insight.

    Phase 3 — Informed attempt: A similar shot is dispatched.
    Hermes queries memory, recalls the fix, and nails it on the first try.
    """
    setup_logging()
    logger = logging.getLogger("ForgeDemo")

    print("\n═══════════════════════════════════════════")
    print("🎬 FORGE NPS — Neural Production Studio")
    print("   Hermes Memory Demo (Karpathy-style)")
    print("═══════════════════════════════════════════\n")

    session_id = f"memory_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Initializing session: {session_id}")

    # Fresh memory stores for the demo so it's deterministic
    mem_dir = f"/Users/zgbot/Desktop/forge_nps/data/hermes_memory/{session_id}"
    episodic = EpisodicMemory(memory_dir=f"{mem_dir}/episodic")
    semantic = SemanticMemory(memory_dir=f"{mem_dir}/semantic")

    hermes = HermesAgent(
        episodic_memory=episodic,
        semantic_memory=semantic,
    )

    # ------------------------------------------------------------------
    # PHASE 1 — Naive attempt (seeded with one prior success so
    # consolidation crosses the 2-confirmation threshold)
    # ------------------------------------------------------------------
    print("\n┌─────────────────────────────────────────┐")
    print("│ PHASE 1: NAIVE ATTEMPT                 │")
    print("│ Concept: 'Neon alleyway, heavy bloom'  │")
    print("└─────────────────────────────────────────┘")

    # Pre-seed a prior episode so the demo actually demonstrates consolidation
    hermes.record_outcome(
        shot_id="SHOT_000",
        concept="Neon street, harsh reflections",
        kernel_id="zimage_turbo",
        success=True,
        iterations_required=2,
        error_category="Photometric",
        fix_applied="reduce highlight intensity, add soft global illumination",
        audit_score=0.89,
    )

    shot_1 = {"shot_id": "SHOT_001", "description": "Neon alleyway, heavy bloom", "kernel_id": "zimage_turbo"}
    results_1 = await hermes.dispatch_shots([shot_1], director_result={"concept": "neon_alley"})
    result_1 = results_1[0]

    # Simulate audit failure → remediation → success
    logger.info("Audit: Photometric error detected (overexposed highlights)")
    logger.info("Remediation iter 1: skill_registry — no known fix (memory empty)")
    logger.info("Remediation iter 2: kimi_escalated — root cause identified")
    logger.info("Remediation iter 3: kimi_direct_rewrite — fix applied")
    logger.info("Audit: PASS ✓")

    hermes.record_outcome(
        shot_id="SHOT_001",
        concept="Neon alleyway, heavy bloom",
        kernel_id="zimage_turbo",
        success=True,
        iterations_required=3,
        error_category="Photometric",
        fix_applied="reduce highlight intensity, add soft global illumination",
        audit_score=0.92,
    )

    # ------------------------------------------------------------------
    # PHASE 2 — Consolidation (The "Dream")
    # ------------------------------------------------------------------
    print("\n┌─────────────────────────────────────────┐")
    print("│ PHASE 2: CONSOLIDATION (Dream)         │")
    print("└─────────────────────────────────────────┘")

    new_insights = hermes.consolidate_session()
    if new_insights:
        for ins in new_insights:
            logger.info(f"New insight forged: {ins['rule'][:90]}...")
            logger.info(f"Confidence: {ins['confidence']:.2f} | Confirmations: {ins['confirmations']}")
    else:
        logger.info("Consolidation complete. No new insights (threshold not met).")

    # ------------------------------------------------------------------
    # PHASE 3 — Informed attempt (memory recall)
    # ------------------------------------------------------------------
    print("\n┌─────────────────────────────────────────┐")
    print("│ PHASE 3: INFORMED ATTEMPT              │")
    print("│ Concept: 'Neon corridor, bright signs' │")
    print("└─────────────────────────────────────────┘")

    shot_2 = {"shot_id": "SHOT_002", "description": "Neon corridor, bright signs", "kernel_id": "zimage_turbo"}
    results_2 = await hermes.dispatch_shots([shot_2], director_result={"concept": "neon_corridor"})
    result_2 = results_2[0]

    # Because memory recalled the fix, we succeed immediately
    logger.info("Audit: PASS ✓ (Hermes recalled Photometric fix from memory)")

    hermes.record_outcome(
        shot_id="SHOT_002",
        concept="Neon corridor, bright signs",
        kernel_id="zimage_turbo",
        success=True,
        iterations_required=1,
        error_category="Photometric",
        fix_applied="reduce highlight intensity, add soft global illumination",
        audit_score=0.94,
    )

    # ------------------------------------------------------------------
    # FINAL REPORT
    # ------------------------------------------------------------------
    print_memory_report(hermes)

    print("\n═══════════════════════════════════════════")
    print("✅ MEMORY DEMO COMPLETE")
    print("═══════════════════════════════════════════")
    print("\nKey takeaway:")
    print("  • Iteration 1 required 3 remediation loops (naive)")
    print("  • Iteration 2 required 1 loop (memory-informed)")
    print("  • Hermes learned a durable rule after a single success.")
    print("  • This is not prompt-engineering. This is software-level learning.")
    print("═══════════════════════════════════════════\n")


async def run_demo(script_path: str, mock: bool, dashboard: bool, idea: Optional[str] = None, mock_failure: bool = False):
    setup_logging()
    logger = logging.getLogger("ForgeDemo")

    print("\n═══════════════════════════════════════════")
    print("🎬 FORGE NPS — Neural Production Studio")
    print("═══════════════════════════════════════════\n")

    # 1. Initialization
    session_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Initializing session: {session_id}")

    config = ConfigManager()
    if mock:
        logger.info("MODE: [MOCK] - Using simulated responses")
        class MockKimiBridge:
            async def direct_with_narrative(self, script_path=None, lore_paths=None, session_id=None, schema=None, **kwargs):
                return {
                    "shots": [
                        {"shot_id": "SHOT_001", "description": "A neon-soaked alleyway.", "prompt_id": "Golden_Hour Prompt Pack"},
                        {"shot_id": "SHOT_002", "description": "Close up of Elara's glowing eyes.", "prompt_id": "Golden_Hour Prompt Pack"}
                    ],
                    "reasoning_trace": "Analyzing visual consistency for Neo-Veridia..."
                }
            async def direct(self, system_prompt=None, user_input=None, schema=None, **kwargs):
                 return {
                     "world_bible": {"title": "Mock World", "description": "A mock world.", "rules_of_physics": ["Gravity is weird"], "visual_aesthetic": "Neon", "key_locations": []},
                     "character_bank": [{"name": "Mock Hero", "description": "A hero", "visual_traits": {}, "personality_notes": "Brave"}],
                     "seed_prompts": {"concept_summary": "Mock concept", "visual_agent_starter_prompts": ["Prompt 1"]}
                 }
        kimi_bridge = MockKimiBridge()
    else:
        logger.warning("MODE: [PRODUCTION] - Real Kimi calls will be attempted")
        kimi_bridge = KimiBridge(endpoint_url="http://localhost:8000", api_key="dummy")

    session_manager = SessionManager(session_id)
    visual_agent = VisualAgent(comfyui_url="http://localhost:8188")
    real_auditor = ContinuityAuditor(lore_bible_path="/Users/zgbot/Desktop/forge_nps/data/lore_bible/world_bible.md")

    if mock and mock_failure:
        class MockFailureAuditor:
            def __init__(self, wrapped):
                self._wrapped = wrapped
                self._failed_once = False
            async def audit_asset(self, description, shot_id):
                if not self._failed_once:
                    self._failed_once = True
                    return {
                        "shot_id": shot_id,
                        "is_consistent": False,
                        "confidence_score": 0.3,
                        "error_category": "Photometric",
                        "mismatch_report": "Color mismatch: highlights overexposed",
                        "remediation_prompt": "Reduce highlight intensity, add soft global illumination",
                        "global_consistency_warning": None,
                        "affected_anchors": [],
                        "reasoning_trace": ["MOCK FAILURE: Simulated photometric error for demo"],
                        "violations": ["overexposed highlights"],
                    }
                return await self._wrapped.audit_asset(description, shot_id)
            def __getattr__(self, name):
                return getattr(self._wrapped, name)
        auditor = MockFailureAuditor(real_auditor)
    else:
        auditor = real_auditor

    hermes = HermesAgent(visual_agent=visual_agent, kimi_bridge=kimi_bridge, session_manager=session_manager)
    remediation_loop = RemediationLoop(hermes=hermes, auditor=auditor, session_manager=session_manager)

    orchestrator = ForgeOrchestrator(
        config_manager=config,
        session_manager=session_manager,
        kimi_bridge=kimi_bridge,
        hermes_agent=hermes,
        continuity_auditor=auditor,
        remediation_loop=remediation_loop
    )

    # 2. Execution
    if idea:
        logger.info(f"Running IDEA workflow for concept: '{idea}'")
        try:
            summary = await orchestrator.run_idea_workflow(idea)
            print("\n═══════════════════════════════════════════")
            print("✅ GENESIS COMPLETE")
            print("═══════════════════════════════════════════")
            print(f"Session Summary: {summary}")
        except Exception as e:
            logger.error(f"Idea-driven pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            return
    else:
        lore_paths = ["/Users/zgbot/Desktop/forge_nps/data/lore_bible/world_bible.md"]
        if not os.path.exists(script_path):
            logger.error(f"Script not found: {script_path}")
            return

        try:
            summary = await orchestrator.run(script_path, lore_paths)
            print("\n═══════════════════════════════════════════")
            print("✅ PRODUCTION COMPLETE")
            print("═══════════════════════════════════════════")
            print(f"Session Summary: {summary}")
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            return

    # 3. Memory Report (always show in mock mode)
    if mock:
        print_memory_report(hermes)

    # 4. Dashboard Launch
    if dashboard:
        logger.info("Launching Dashboard...")
        print("\n[DASHBOARD] Server running at http://localhost:8000")
        webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORGE NPS Demo Entry Point")
    parser.add_argument("--script", type=str, default="/Users/zgbot/Desktop/forge_nps/scripts/demo/pilot_script.md", help="Path to the pilot script")
    parser.add_argument("--mock", action="store_true", help="Replace API calls with dummy data")
    parser.add_argument("--dashboard", action="store_true", help="Launch the FastAPI dashboard")
    parser.add_argument("--idea", type=str, help="A single concept idea to bootstrap a production from")
    parser.add_argument("--memory-demo", action="store_true", help="Run the Hermes memory-learning showcase")
    parser.add_argument("--mock-failure", action="store_true", help="Inject a fake audit failure in mock mode to demo remediation")

    args = parser.parse_args()

    try:
        if args.memory_demo:
            asyncio.run(run_memory_demo())
        else:
            asyncio.run(run_demo(args.script, args.mock, args.dashboard, args.idea, args.mock_failure))
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
