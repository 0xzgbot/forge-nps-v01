import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable

from core.hermes.memory import EpisodicMemory, SemanticMemory, MemoryConsolidator
from core.consistency.character_consistency_engine import CharacterConsistencyEngine
from core.bridge.nous_hermes_bridge import NousHermesBridge

logger = logging.getLogger("HermesAgent")

# Optional event emitter for dashboard integration.
_event_emitter: Optional[Callable[[str, Dict[str, Any]], Any]] = None

# Maximum total chars for memory injection to prevent self-poisoning.
MEMORY_INJECTION_CAP = 400


def set_event_emitter(emitter: Optional[Callable[[str, Dict[str, Any]], Any]]):
    """Register an async event emitter for Hermes decision events."""
    global _event_emitter
    _event_emitter = emitter


async def _emit(event_type: str, payload: Dict[str, Any]):
    """Emit a Hermes event if an emitter is registered."""
    if _event_emitter is not None:
        try:
            await _event_emitter(event_type, payload)
        except Exception:
            pass


def _build_memory_injection(
    episodic_examples: List[Dict[str, Any]],
    semantic_rules: List[Dict[str, Any]],
    skill_vocab: List[str],
    max_chars: int = MEMORY_INJECTION_CAP,
) -> str:
    """
    Build a labeled, three-block memory injection string.

    Blocks:
      [EPISODIC]  - Past successful examples from episodic memory
      [SEMANTIC]  - Distilled rules from semantic memory
      [SKILLS]    - Relevant skill vocabulary

    Each block is capped proportionally so the total stays under max_chars.
    If a block is empty, its label is omitted.
    """
    blocks = []
    remaining = max_chars

    # --- Block 1: Episodic examples ---
    if episodic_examples:
        block_lines = []
        for evt in episodic_examples[:3]:
            fix = evt.get("fix_applied", "")
            concept = evt.get("concept", "")
            line = f"fix={fix}" if fix and fix.lower() != "none" else f"concept={concept}"
            if line:
                block_lines.append(f"  - {line}")
        if block_lines:
            header = "[EPISODIC]\n"
            content = header + "\n".join(block_lines)
            if len(content) <= remaining:
                blocks.append(content)
                remaining -= len(content)

    # --- Block 2: Semantic rules ---
    if semantic_rules:
        block_lines = []
        for rule in semantic_rules[:3]:
            rule_text = rule.get("rule", "")
            conf = rule.get("confidence", 0)
            line = f"  - ({conf:.0%}) {rule_text}"
            if line:
                block_lines.append(line)
        if block_lines:
            header = "[SEMANTIC]\n"
            content = header + "\n".join(block_lines)
            if len(content) <= remaining:
                blocks.append(content)
                remaining -= len(content)

    # --- Block 3: Skill vocabulary ---
    if skill_vocab:
        vocab_str = ", ".join(skill_vocab[:6])
        header = "[SKILLS]\n  - "
        content = header + vocab_str
        if len(content) <= remaining:
            blocks.append(content)

    return "\n\n".join(blocks)


class HermesAgent:
    """
    The autonomous decision-making layer with Karpathy-style explicit memory.
    """

    def __init__(
        self,
        visual_agent=None,
        skill_registry=None,
        kimi_bridge=None,
        hermes_bridge=None,
        lmstudio_client=None,  # For NousHermesBridge
        session_manager=None,
        episodic_memory: Optional[EpisodicMemory] = None,
        semantic_memory: Optional[SemanticMemory] = None,
        character_engine: Optional[CharacterConsistencyEngine] = None,
    ):
        self.visual_agent = visual_agent
        self.skill_registry = skill_registry
        self.kimi_bridge = kimi_bridge
        self.hermes_bridge = hermes_bridge
        self.session_manager = session_manager
        self.character_engine = character_engine
        self._autonomy_score = 0.0

        # Initialize NousHermesBridge (The Brain)
        if lmstudio_client:
            self.hermes_brain = NousHermesBridge(lmstudio_client)
        else:
            self.hermes_brain = None

        self.episodic = episodic_memory or EpisodicMemory()
        self.semantic = semantic_memory or SemanticMemory()
        self.consolidator = MemoryConsolidator(self.episodic, self.semantic)

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    async def dispatch_shots(
        self,
        shot_list: List[Dict[str, Any]],
        director_result: Dict[str, Any],
        override_prompt: Optional[str] = None,  # FIX: Added for remediation override
    ) -> List[Dict[str, Any]]:
        """
        Dispatch shots to generation.
        FIX: If override_prompt is provided, we skip creative re-generation
        to ensure technical fixes (from remediation) are strictly applied.
        """
        logger.info(f"Hermes: Dispatching {len(shot_list)} shots...")
        await _emit("DISPATCH_START", {"shot_count": len(shot_list)})
        results = []

        for shot in shot_list:
            shot_id = shot.get("shot_id", "UNKNOWN")
            concept = shot.get("description", "")
            intent = shot.get("intent", "high_fidelity_image")
            kernel_id = shot.get("kernel_id", "zimage_turbo")
            error_category = shot.get("error_category")  # For post_failure mode

            await _emit("MEMORY_QUERY", {"shot_id": shot_id, "concept": concept})

            # --- MEMORY RETRIEVAL (Three-block injection) ---

            # Block 1: Episodic examples
            if error_category:
                # Post-failure mode: retrieve successful remediations
                episodic_examples = self.episodic.query_post_failure(
                    concept=concept,
                    error_category=error_category,
                    kernel_id=kernel_id,
                    top_k=2,
                )
            else:
                # Pre-prompt mode: retrieve successful outcomes
                episodic_examples = self.episodic.query_pre_prompt(
                    concept=concept,
                    kernel_id=kernel_id,
                    top_k=2,
                )

            # Block 2: Semantic rules
            semantic_rules = self.semantic.query_relevant(
                error_category=error_category,
                kernel_id=kernel_id,
                min_confidence=0.6,
                min_confirmations=2,
            )

            # Block 3: Skill vocabulary
            skill_vocab = []
            if self.skill_registry:
                # Extract relevant skill names/vocabulary for this context
                if hasattr(self.skill_registry, "get_relevant"):
                    skill_vocab = self.skill_registry.get_relevant(
                        concept=concept, kernel_id=kernel_id
                    )
                elif isinstance(self.skill_registry, dict):
                    skill_vocab = list(self.skill_registry.keys())[:6]

            # Build the labeled injection (capped at 400 chars)
            memory_injection = _build_memory_injection(
                episodic_examples=episodic_examples,
                semantic_rules=semantic_rules,
                skill_vocab=skill_vocab,
                max_chars=MEMORY_INJECTION_CAP,
            )

            # Build backward-compatible augmentation string for bridge calls
            memory_augmentation = ""
            if episodic_examples:
                best = episodic_examples[0]
                if best.get("success") and best.get("fix_applied"):
                    memory_augmentation = f" [Learned: {best['fix_applied']}]"
            if semantic_rules:
                top_rule = semantic_rules[0]["rule"]
                memory_augmentation += f" [Rule: {top_rule[:80]}...]"

            enriched_description = concept + memory_augmentation

            # --- PROMPT DETERMINATION (FIXED LOGIC) ---
            final_creative_prompt = enriched_description
            if self.hermes_bridge:
                try:
                    generated_prompt = await self.hermes_bridge.generate_shot_prompt(
                        concept=enriched_description,
                        director_schema=director_result,
                        memory_context=memory_injection or memory_augmentation
                    )
                    if generated_prompt and "[Hermes-3 Error]" not in generated_prompt:
                        final_creative_prompt = generated_prompt
                        await _emit("PROMPT_WRITTEN", {"shot_id": shot_id, "prompt": final_creative_prompt})
                    else:
                        logger.warning(f"[HERMES-3] Prompt generation failed or returned error for {shot_id}, using enriched concept.")
                except Exception as e:
                    logger.error(f"[HERMES-3] Error calling hermes_bridge for {shot_id}: {e}")
            elif override_prompt:
                # PRIORITY 1: Use the exact technical fix provided by remediation/auditor
                logger.info(f"[HERMES] Using OVERRIDE prompt for shot {shot_id}")
                final_creative_prompt = override_prompt
            elif self.hermes_brain:
                # PRIORITY 2: Use the Brain to generate a high-fidelity cinematic description
                logger.info(f"[HERMES-3 ] Generating creative shot prompt for {shot_id}")
                generated_prompt = await self.hermes_brain.generate_shot_prompt(
                    concept=enriched_description,
                    director_schema=director_result,
                    memory_context=memory_injection or memory_augmentation
                )
                if "[Hermes-3 Error]" not in generated_prompt:
                    final_creative_prompt = generated_prompt
                    await _emit("PROMPT_WRITTEN", {"shot_id": shot_id, "prompt": final_creative_prompt})
                else:
                    logger.warning(f"[HERMES-3] Prompt generation failed for {shot_id}, using enriched concept.")

            # --- DISPATCH TO VISUAL AGENT ---
            logger.info(f"[HERMES] Dispatching shot: {shot_id}")
            await _emit("DISPATCH_SHOT", {"shot_id": shot_id, "prompt": final_creative_prompt})

            if self.visual_agent and hasattr(self.visual_agent, "generate"):
                result = await self.visual_agent.generate(
                    shot_id=shot_id,
                    description=final_creative_prompt,
                    director_schema=director_result,
                )
            else:
                await asyncio.sleep(0.3)
                result = {
                    "shot_id": shot_id,
                    "description": final_creative_prompt,
                    "asset_path": f"data/outputs/demo/{shot_id}.png",
                    "status": "complete",
                }

            results.append(result)

            # REMOVED: self.episodic.record(...) call here to prevent duplicate logging in the Orchestrator.

        await _emit("DISPATCH_COMPLETE", {"shot_count": len(shot_list)})
        return results

    def record_outcome(
        self,
        shot_id: str,
        concept: str,
        kernel_id: str,
        success: bool,
        iterations_required: int,
        error_category: Optional[str] = None,
        fix_applied: Optional[str] = None,
        audit_score: float = 0.0,
        source: str = "live",
    ):
        """Record a final_outcome event. Uses canonical event type."""
        self.episodic.record({
            "session_id": getattr(self.session_manager, "session_id", "unknown"),
            "shot_id": shot_id,
            "event_type": "final_outcome",
            "concept": concept,
            "kernel_id": kernel_id,
            "success": success,
            "iterations_required": iterations_required,
            "error_category": error_category or "general",
            "fix_applied": fix_applied or "none",
            "audit_score": audit_score,
        }, source=source)
        logger.info(
            f"[HERMES MEMORY] Recorded outcome for {shot_id}: "
            f"success={success}, iterations={iterations_required}, source={source}"
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_emit("OUTCOME_RECORD", {
                "shot_id": shot_id,
                "success": success,
                "score": audit_score,
                "error_category": error_category,
                "fix": fix_applied,
            }))
        except RuntimeError:
            pass

    def record_remediation(
        self,
        shot_id: str,
        concept: str,
        kernel_id: str,
        error_category: str,
        fix_applied: str,
        success: bool,
        audit_score: float = 0.0,
        source: str = "live",
    ):
        """Record a remediation event. Uses canonical event type."""
        self.episodic.record({
            "session_id": getattr(self.session_manager, "session_id", "unknown"),
            "shot_id": shot_id,
            "event_type": "remediation",
            "concept": concept,
            "kernel_id": kernel_id,
            "success": success,
            "iterations_required": 1,
            "error_category": error_category,
            "fix_applied": fix_applied,
            "audit_score": audit_score,
        }, source=source)
        logger.info(
            f"[HERMES MEMORY] Recorded remediation for {shot_id}: "
            f"error={error_category}, fix={fix_applied[:60]}, success={success}, source={source}"
        )

    async def consolidate_session(self, session_events: List[Dict[str, Any]] = None):
        await _emit("CONSOLIDATION_START", {"event_count": len(session_events) if session_events else "all"})
        new_insights = self.consolidator.consolidate(session_events)
        if new_insights:
            logger.info(f"[HERMES MEMORY] Consolidated {len(new_insights)} new insights")
            for ins in new_insights:
                await _emit("INSIGHT_BORN", {
                    "insight_id": ins.get("insight_id", ""),
                    "rule": ins.get("rule", ""),
                    "confidence": ins.get("confidence", 0),
                })
        return new_insights

    def get_memory_summary(self) -> Dict[str, Any]:
        return {
            "episodic_stats": self.episodic.get_stats(),
            "semantic_stats": self.semantic.get_stats(),
            "autonomy_score": self._autonomy_score,
        }

    def get_recent_experiences(self, n: int = 5) -> List[Dict[str, Any]]:
        return self.episodic.get_recent(n)

    def get_active_rules(self) -> List[Dict[str, Any]]:
        return self.semantic.get_all_insights()

    @property
    def autonomy_score(self) -> float:
        return self._autonomy_score

    def set_autonomy_score(self, score: float):
        self._autonomy_score = score
