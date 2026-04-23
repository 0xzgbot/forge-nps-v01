from core.parsing.kimi_payload_parser import KimiPayloadParser
from core.bridge.kimi_model_router import KimiModelRouter, ModelTier
from core.prompts.director_system_prompt import DIRECTOR_SYSTEM_PROMPT, PREDICTION_ADDENDUM

import os
import json
import httpx
import logging
from typing import Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KimiBridge")

T = TypeVar("T", bound=BaseModel)

class StrictSchemaGuard:
    """
    Enforces Pydantic schema validation on Kimi's JSON output.
    If validation fails, it generates a remediation prompt for one retry.
    """
    @staticmethod
    def validate(data: Any, schema: Type[T]) -> T:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON string: {e}")
        
        return schema.model_validate(data)

    @staticmethod
    def get_remediation_prompt(error: ValidationError, raw_content: str) -> str:
        """Generates a prompt to help Kimi fix its own schema errors."""
        errors = error.errors()
        error_details = []
        for err in errors:
            loc = " -> ".join(str(x) for x in err["loc"])
            msg = err["msg"]
            error_details.append(f"- {loc}: {msg}")
        
        details_str = "\n".join(error_details)
        return (
            "Your previous response failed schema validation. Please correct the errors and return only valid JSON.\n\n"
            "Errors encountered:\n"
            f"{details_str}\n\n"
            "Current incorrect content:\n"
            f"```json\n{raw_content}\n```"
        )

class KimiBridge:
    """
    Handles high-context communication with Kimi K2.5 via NVIDIA NIM endpoints.
    Designed for 'Directing' workflows requiring massive context and structured JSON.
    """
    def __init__(self, endpoint_url: str, api_key: str, config_manager: Any):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.config_manager = config_manager
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def direct(
        self, 
        system_prompt: str, 
        user_input: str, 
        schema: Type[BaseModel],
        context_files: list[str] = None,
        retry_on_validation_error: bool = True,
        task_description: Optional[str] = None,
        has_visuals: bool = False
    ) -> Dict[str, Any]:
        """
        The primary entry point for the 'Director' role. 
        Injects context files (Lore Bible), enforces JSON output, and validates against a Pydantic schema.
        """
        context_text = ""
        if context_files:
            for file_path in context_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_text += f"\n--- FILE: {os.path.basename(file_path)} ---\n{f.read()}\n"
                except Exception as e:
                    logger.error(f"Failed to read context file {file_path}: {e}")

        full_prompt = f"{context_text}\n\n{user_input}"
        return await self._execute_request(system_prompt, full_prompt, schema, retry_on_validation_error, task_description=task_description, has_visuals=has_visuals)

    async def direct_with_narrative(
        self, 
        script_path: str, 
        lore_paths: list[str], 
        session_id: str, 
        schema: Type[BaseModel],
        skill_registry: Optional['SkillRegistry'] = None
    ) -> Dict[str, Any]:
        """
        Full narrative analysis mode (1M context window use case).
        Constructs a mega-prompt following the critical [WORLD BIBLE] -> [CHARACTER REGISTRY] -> [FULL SCRIPT] -> [HISTORICAL SKILL LEARNINGS] -> [DIRECTOR TASK v2] order.
        """
        from core.script.script_parser import ScriptParser
        from core.skills.skill_registry import SkillRegistry

        try:
            # 1. Parse the full script using ScriptParser (J10)
            parser = ScriptParser()
            parsed_script = parser.parse(script_path)
            script_content = parsed_script["full_text"]
            
            # Extract Character Registry from parsed script for the prompt
            char_registry_str = "\n".join([f"- {c}" for c in parsed_script["character_registry"]])

            # 2. Load all files from lore_paths (World Bible, etc.)
            lore_text = ""
            for path in lore_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lore_text += f"\n--- FILE: {os.path.basename(path)} ---\n{f.read()}\n"
                except Exception as e:
                    logger.warning(f"Failed to read lore file {path}: {e}")

            # 3. Retrieve historical skill learnings/best practices from SkillRegistry (J6)
            skill_learnings = ""
            if skill_registry:
                # We'll grab all current fixes as 'historical learnings'
                learnings_data = skill_registry.data.get("fixes", {})
                if learnings_data:
                    skill_learnings += "\n[HISTORICAL SKILL LEARNINGS]\n"
                    for key, info in learnings_data.items():
                        # Only include "stable" learnings (confirmations > 2) to avoid noise in the mega-prompt
                        if info.get("confirmations", 0) > 2:
                            skill_learnings += f"- For {key}: Apply '{info['prompt_modifier']}' (Reasoning: {info['kimi_reasoning']})\n"

            # 4. Construct "Mega-Prompt" with strict context ordering for maximum Kimi attention:
            # [WORLD BIBLE] -> [CHARACTER REGISTRY] -> [FULL SCRIPT] -> [HISTORICAL SKILL LEARNINGS] -> [DIRECTOR TASK (v2)]
            mega_prompt = (
                f"[WORLD BIBLE]\n{lore_text}\n\n"
                f"[CHARACTER REGISTRY]\n{char_registry_str}\n\n"
                f"[FULL SCRIPT]\n{script_content}\n\n"
                f"{skill_learnings}\n\n"
                f"[DIRECTOR TASK (v2)]\n"
                f"Analyze the provided script and lore to generate a high-fidelity Director Schema. "
                f"Ensure character consistency, visual continuity, and adherence to historical best practices."
            )

            # 5. Use the DIRECTOR_SYSTEM_PROMPT and PREDICTION_ADDENDUM from core/prompts/director_system_prompt.py (J3)
            full_system_prompt = f"{DIRECTOR_SYSTEM_PROMPT}\n\n{PREDICTION_ADDENDUM}"

            # 6. Token count estimation (Hackathon talking point)
            # Simple approximation: ~4 chars per token for English text
            estimated_tokens = len(mega_prompt.encode('utf-8')) // 4
            
            # Log reasoning trace and estimation to the session directory
            log_dir = os.path.abspath(os.path.join("~/Desktop/forge_nps/data/reasoning_logs", session_id))
            os.makedirs(log_dir, exist_ok=True)
            
            estimation_log_path = os.path.join(log_dir, "token_estimation.md")
            with open(estimation_log_path, 'w', encoding='utf-8') as f:
                f.write(f"# Token Estimation Trace - Session {session_id}\n\n")
                f.write(f"- **Estimated Tokens:** ~{estimated_tokens}\n")
                f.write(f"- **Context Window Usage:** {(estimated_tokens / 1000000) * 100:.4f}% of 1M window\n")

            logger.info(f"[{session_id}] Estimated Mega-Prompt tokens: ~{estimated_tokens}")

            # 7. Execute the request via NIM
            result = await self._execute_request(full_system_prompt, mega_prompt, schema)

            # 8. Save the generated narrative_reasoning_trace to data/reasoning_logs/{session_id}/full_analysis_reasoning.md
            # Check if reasoning trace is in result (returned by Kimi or via schema)
            trace_content = result.get("narrative_reasoning_trace") or result.get("reasoning_trace", "No reasoning trace provided.")
            log_path = os.path.join(log_dir, "full_analysis_reasoning.md")
            
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"# Narrative Reasoning Trace - Session {session_id}\n\n")
                f.write(trace_content)
            
            logger.info(f"Reasoning trace saved to {log_path}")

            return result

        except Exception as e:
            logger.error(f"direct_with_narrative failed: {e}")
            raise

    async def analyze_failure(self, shot_id: str, audit_result: Dict[str, Any], original_directive: Dict[str, Any], lore_paths: list[str], schema: Type[BaseModel]) -> Dict[str, Any]:
        """
        Post-failure analysis mode for remediation.
        Kimi receives the intended directive, the actual audit result, and the lore bible.
        """
        try:
            lore_text = ""
            for path in lore_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lore_text += f"\n--- LORE FILE: {os.path.basename(path)} ---\n{f.read()}\n"
                except Exception as e:
                    logger.warning(f"Failed to read lore file {path}: {e}")

            system_prompt = "You are the FORGE Remediation Engine. Your task is to analyze why a shot failed to meet its directive and provide a correction."
            
            user_input = (
                f"FAILURE ANALYSIS REQUEST\n"
                f"Shot ID: {shot_id}\n\n"
                f"[ORIGINAL DIRECTIVE]\n{json.dumps(original_directive, indent=2)}\n\n"
                f"[AUDIT RESULT / MISMATCH REPORT]\n{json.dumps(audit_result, indent=2)}\n\n"
                f"[LORE CONTEXT]\n{lore_text}\n\n"
                f"Please identify the root cause, specify the fix type (e.g., prompt_adjustment, lore_contradiction, technical_constraint), "
                f"provide a corrected directive, and suggest any necessary skill/model updates."
            )

            # We use a generic schema for remediation if one isn't provided, 
            # but the requirement implies it returns a dict with specific keys.
            # Let's assume we pass a schema or just return the dict from Kimi.
            return await self._execute_request(system_prompt, user_input, schema)

        except Exception as e:
            logger.error(f"analyze_failure failed: {e}")
            raise

    async def _execute_request(
        self, 
        system_prompt: str, 
        user_input: str, 
        schema: Type[BaseModel],
        retry_on_validation_error: bool = True,
        is_retry: bool = False,
        task_description: Optional[str] = None,
        has_visuals: bool = False
    ) -> Dict[str, Any]:
        from core.bridge.kimi_model_router import KimiModelRouter
        
        # 1. Routing Decision
        router = KimiModelRouter(self.config_manager) # Note: requires config_manager to be passed in __init__
        tier = router.route(task_description or user_input, has_visuals=has_visuals)
        model_name = router.get_model_endpoint(tier)
        
        logger.info(f"Routing request to {tier.value} ({model_name})")

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2 if tier != ModelTier.INSTRUCT else 0.7 
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                logger.info("Sending request to Kimi...")
                response = await client.post(self.endpoint_url, headers=self.headers, json=payload)
                response.raise_for_status()
                
                data = response.json()
                content_str = data['choices'][0]['message']['content']
                
                try:
                    validated_data = StrictSchemaGuard.validate(content_str, schema)
                    return validated_data.model_dump()
                except (ValidationError, ValueError) as e:
                    if retry_on_validation_error and not is_retry:
                        logger.warning(f"Validation failed: {e}. Attempting remediation...")
                        err_obj = e if isinstance(e, ValidationError) else ValidationError.from_exception(e)
                        remediation_prompt = StrictSchemaGuard.get_remediation_prompt(err_obj, content_str)
                        
                        return await self._execute_request(
                            system_prompt, 
                            remediation_prompt, 
                            schema, 
                            retry_on_validation_error, 
                            is_retry=True,
                            task_description=task_description,
                            has_visuals=has_visuals
                        )
                    else:
                        # Fallback to parsing...
                        try:
                            logger.info("Attempting KimiPayloadParser fallback for non-JSON content.")
                            parser = KimiPayloadParser()
                            parsed_data = parser.parse_audit_v2(content_str)
                            if parsed_data:
                                logger.warning("Kimi returned non-JSON — successfully parsed via KimiPayloadParser")
                                try:
                                    validated_parsed = schema.model_validate(parsed_data)
                                    return validated_parsed.model_dump()
                                except Exception as validation_err:
                                    logger.warning(f"Parsed data from fallback failed schema validation: {validation_err}. Returning raw parsed dict.")
                                    return parsed_data
                        except Exception as parse_err:
                            logger.error(f"Fallback parsing also failed: {parse_err}")

                        logger.error("Validation failed and no retries/fallback possible.")
                        raise e

            except Exception as e:
                logger.error(f"Kimi Bridge Error: {e}")
                raise

if __name__ == "__main__":
    # Test placeholder
    print("KimiBridge module loaded.")
