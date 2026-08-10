from core.bridge.kimi_bridge import KimiBridge, StrictSchemaGuard
from core.bridge.kimi_model_router import ModelTier
from pydantic import BaseModel
import base64
import os
import logging
import httpx
from typing import Dict, Any, Optional, Type

logger = logging.getLogger("KimiVLClient")

class KimiVLClient(KimiBridge):
    """
    Specialized client for multi-modal reasoning (Kimi-VL).
    Extends KimiBridge to handle image/video data payloads.
    """

    async def analyze_visuals(
        self,
        image_path: str,
        system_prompt: str,
        user_prompt: str,
        schema: Type[BaseModel],
        task_description: Optional[str] = None,
        retry_on_validation_error: bool = True
    ) -> Dict[str, Any]:
        """
        Sends an image alongside a prompt to Kimi-VL for high-precision visual reasoning.
        Used primarily by the QA Agent for consistency audits and the Editor for polish verification.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Visual asset not found at: {image_path}")

        # 1. Encode image to base64
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # 2. Construct multi-modal payload
        # Note: Structure follows standard OpenAI-compatible vision API format used by many NIM providers
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1 # Low temperature for rigorous visual audits
        }

        # 3. Execute via the upgraded _execute_request to leverage ModelRouter
        return await self._execute_visual_request(payload, schema, task_description, retry_on_validation_error)

    async def _execute_visual_request(
        self,
        payload: Dict[str, Any],
        schema: Type[BaseModel],
        task_description: Optional[str] = None,
        retry_on_validation_error: bool = True
    ) -> Dict[str, Any]:
        """
        Internal method to handle the visual-specific HTTP call while maintaining 
        routing and validation logic from the parent bridge.
        """
        from core.bridge.kimi_model_router import KimiModelRouter

        # 1. Routing Decision (Force VISUAL tier for multi-modal)
        router = KimiModelRouter(self.config_manager)
        tier = ModelTier.VISUAL
        model_name = router.get_model_endpoint(tier)
        
        logger.info(f"Routing visual request to {tier.value} ({model_name})")
        payload["model"] = model_name

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(self.endpoint_url, headers=self.headers, json=payload)
                response.raise_for_status()
                
                data = response.json()
                content_str = data['choices'][0]['message']['content']
                
                # 2. Validate via StrictSchemaGuard (Inherited from KimiBridge)
                try:
                    validated_data = StrictSchemaGuard.validate(content_str, schema)
                    return validated_data.model_dump()
                except Exception as e:
                    if retry_on_validation_error:
                        logger.warning(f"Visual validation failed: {e}. Attempting remediation...")
                        # In a real implementation, we'd construct a text-only remediation prompt 
                        # describing the visual context + the error to Kimi.
                        return await self._handle_visual_remediation(content_str, schema, payload)
                    raise e

            except Exception as e:
                logger.error(f"KimiVLClient Error: {e}")
                raise
    async def _handle_visual_remediation(self, failed_content: str, schema: Type[BaseModel], original_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback logic to fix JSON errors in visual reasoning tasks.
        Constructs a text-only remediation request that describes the failure and requests a correction.
        """
        logger.info("Attempting visual remediation loop...")
        
        # Extract user prompt from original payload to maintain context
        user_prompt = ""
        for msg in original_payload.get("messages", []):
            if msg["role"] == "user":
                for part in msg["content"]:
                    if part["type"] == "text":
                        user_prompt += part["text"]

        remediation_system_prompt = (
            "You are the CINESMITH Visual Remediation Engine. Your task is to correct a JSON formatting error "
            "that occurred during a visual analysis task. You must strictly adhere to the requested schema."
        )

        remediation_user_input = (
            f"CRITICAL: Your previous response failed JSON schema validation.\n\n"
            f"[ORIGINAL TASK CONTEXT]\n{user_prompt}\n\n"
            f"[FAILED CONTENT TO BE FIXED]\n```json\n{failed_content}\n```\n\n"
            f"Please re-evaluate the visual context and provide a corrected JSON response. "
            f"Ensure all keys are present and correctly typed according to the schema."
        )

        # We use direct() for remediation because it handles standard text-based retry logic
        # and we've already extracted the essential context from the original payload.
        try:
            # Since this is a text-based fix of a multi-modal error, we treat it as a 'direct' call
            # to leverage the existing KimiBridge retry/remediation logic if needed.
            return await self.direct(
                system_prompt=remediation_system_prompt,
                user_input=remediation_user_input,
                schema=schema,
                retry_on_validation_error=False # Prevent infinite recursion
            )
        except Exception as e:
            logger.error(f"Visual remediation failed: {e}")
            raise


    async def audit_frame(
        self,
        image_base64: str,
        mime_type: str,
        expected_description: str,
        lore_excerpt: str,
        shot_id: str,
    ) -> dict:
        """
        Audit a single video frame sent from the browser.
        image_base64: Raw base64 string (NO data: URI prefix)
        mime_type: image/jpeg or image/png
        """
        import logging
        from pydantic import BaseModel

        logger = logging.getLogger("KimiVLClient")
        
        image_data_url = f"data:{mime_type};base64,{image_base64}"
        
        prompt = (
            f"You are a Visual Continuity Auditor for a film production pipeline.\n\n"
            f"LORE BIBLE EXCERPT:\n{lore_excerpt}\n\n"
            f"EXPECTED SHOT DESCRIPTION:\n{expected_description}\n\n"
            f"TASK:\nExamine the attached rendered frame. Compare it against the lore bible and expected description above.\n\n"
            f"Check for these specific categories of error:\n"
            f"1. CHARACTER: Does the character match their defined appearance (hair, eyes, clothing, signature items)?\n"
            f"2. LIGHTING: Does the lighting match the described mood/time of day?\n"
            f"3. PROP: Are key props present and correct?\n"
            f"4. BACKGROUND: Does the environment match the setting?\n"
            f"5. ANATOMY: Are hands, faces, and proportions correct?\n"
            f"6. STYLE: Does the image match the stated aesthetic (e.g., cinematic, anime, photoreal)?\n\n"
            f"Respond in this exact JSON format:\n"
            f"{{\n"
            f"  \"is_consistent\": true or false,\n"
            f"  \"confidence_score\": 0.0 to 1.0,\n"
            f"  \"error_category\": \"character\" | \"lighting\" | \"prop\" | \"background\" | \"anatomy\" | \"style\" | \"other\" | null,\n"
            f"  \"mismatch_details\": \"Brief description of what is wrong, if anything. Be specific.\",\n"
            f"  \"suggested_fix\": \"Specific prompt adjustment to fix the issue, or null if consistent.\"\n"
            f"}}"
        )

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {"type": "text", "text": prompt},
                    ]
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        class AuditResult(BaseModel):
            is_consistent: bool | None
            confidence_score: float
            error_category: str | None
            mismatch_details: str
            suggested_fix: str | None

        try:
            verdict = await self._execute_visual_request(
                payload=payload,
                schema=AuditResult,
                task_description=f"Visual audit for shot {shot_id}"
            )
            return verdict
        except Exception as e:
            logger.error(f"Kimi frame audit failed: {e}")
            if "429" in str(e):
                return {
                    "is_consistent": None,
                    "confidence_score": 0.0,
                    "error_category": "rate_limited",
                    "mismatch_details": "Kimi VL rate limit hit. Retry later.",
                    "suggested_fix": None,
                }
            raise e


if __name__ == "__main__":
    print("KimiVLClient module loaded.")
