import asyncio
import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger("AssetPromptGenerator")

class AssetPromptGenerator:
    """
    J9: Asset Prompt Generation & Batching Logic.
    Transforms a parsed Pilot Script into high-fidelity, cinematic 
    prompt batches optimized for FLUX and LTX/Video generation.
    """

    def __init__(self, kimi_bridge):
        self.kimi = kimi_bridge
        # Cinematic parameter templates (to be expanded based on project standards)
        self.camera_presets = {
            "wide": "low angle wide shot, cinematic scale, deep depth of field",
            "close_up": "extreme close-up, shallow depth of field, macro detail, intense focus",
            "medium": "eye-level medium shot, naturalistic framing",
            "tracking": "dynamic tracking shot, smooth gimbal motion, following movement",
            "drone": "high altitude aerial view, sweeping cinematic pan, wide perspective"
        }
        self.lighting_presets = [
            "volumetric lighting, dramatic shadows, high contrast",
            "golden hour, soft natural glow, warm highlights",
            "cyberpunk neon saturation, teal and magenta rim lighting",
            "noir aesthetic, harsh chiaroscuro, monochromatic mood"
        ]

    async def generate_prompts_from_script(self, script_data: Dict[str, Any], bible_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        The primary orchestration method for J9.
        1. Decomposes scenes into individual shots.
        2. Generates descriptive prompts using Kimi/LLM logic.
        3. Injects cinematic parameters (Lens, Motion, Lighting).
        4. Returns a batch of structured prompt payloads.
        """
        logger.info("Starting Asset Prompt Generation from script...")
        
        scenes = script_data.get('scenes', [])
        if not scenes:
            logger.warning("No scenes found in script data.")
            return []

        prompt_batch = []

        for scene_idx, scene in enumerate(scenes):
            # 1. Decompose Scene into Shots (Simulated/LLM-driven)
            # In a full implementation, we'd ask Kimi to 'break this scene into X shots'
            shots = await self._decompose_scene_to_shots(scene, bible_data)

            for shot_idx, shot in enumerate(shots):
                # 2. Build the base visual description
                base_description = f"{shot['subject']}, {shot['action']}, {shot['environment']}"
                
                # 3. Inject Cinematic Parameters (The 'Secret Sauce')
                cinematic_prompt = self._apply_cinematic_standard(
                    base_description, 
                    shot['camera_preset'], 
                    shot['lighting_style']
                )

                # 4. Construct the Final Payload
                payload = {
                    "id": f"scene_{scene_idx+1}_shot_{shot_idx+1}",
                    "scene_index": scene_idx + 1,
                    "base_prompt": cinematic_prompt,
                    "metadata": {
                        "subject": shot['subject'],
                        "camera": shot['camera_preset'],
                        "lighting": shot['lighting_style'],
                        "environment": shot['environment']
                    }
                }
                prompt_batch.append(payload)

        logger.info(f"Generated {len(prompt_batch)} total shots for prompting.")
        return prompt_batch

    async def _decompose_scene_to_shots(self, scene: Dict[str, Any], bible_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Uses Kimi to take a single script scene and break it into 3-5 distinct visual shots.
        This ensures variety in the final asset batch.
        """
        # Constructing the reasoning prompt for Kimi
        system_prompt = (
            "You are a Cinematographer and Shot Director. "
            "Your task is to take a single narrative scene and decompose it into a sequence of distinct visual shots. "
            "Each shot must have: Subject, Action, Environment, Camera Preset, and Lighting Style."
        )
        
        user_prompt = f"""
        WORLD BIBLE CONTEXT:
        {bible_data.get('content', 'Generic setting')}

        SCENE DESCRIPTION:
        Time: {scene.get('time', 'Unknown')}
        Visuals: {scene.get('visuals', 'No visuals provided')}
        Action: {scene.get('action', 'No action provided')}

        OUTPUT FORMAT (JSON Array of objects):
        [
          {{
            "subject": "...",
            "action": "...",
            "environment": "...",
            "camera_preset": "wide|close_up|medium|tracking|drone",
            "lighting_style": "cinematic|neon|golden_hour|noir"
          }}
        ]
        """

        # Note: In a real run, we call Kimi. Here we provide a fallback for testing.
        try:
            response = await self.kimi.direct(system_prompt=system_prompt, user_prompt=user_prompt)
            # Parse the JSON from Kimi's response (handling potential markdown wrappers)
            json_str = re.search(r'\[.*\]', response, re.DOTALL)
            if json_str:
                import json
                return json.loads(json_str.group())
            else:
                raise ValueError("No JSON array found in Kimi response.")
        except Exception as e:
            logger.error(f"Kimi decomposition failed: {e}. Using fallback shots.")
            # Fallback logic for demonstration/testing purposes
            return [
                {
                    "subject": scene.get('visuals', 'Character'),
                    "action": scene.get('action', 'standing still'),
                    "environment": "cinematic environment",
                    "camera_preset": "wide",
                    "lighting_style": "cinematic"
                }
            ]

    def _apply_cinematic_standard(self, description: str, camera: str, lighting: str) -> str:
        """
        Applies the heavy-duty FLUX/LTX prompting standards.
        Ensures no generic 'cinematic' terms are used without specific descriptors.
        """
        cam_desc = self.camera_presets.get(camera, self.camera_presets['medium'])
        
        # Map lighting keyword to full descriptor
        light_map = {
            "cinematic": self.lighting_presets[0],
            "neon": self.lighting_presets[2],
            "golden_hour": self.lighting_presets[1],
            "noir": self.lighting_presets[3]
        }
        light_desc = light_map.get(lighting, self.lighting_presets[0])

        # Final assembly: [Subject/Action/Environment], [Camera Detail], [Lighting Detail], [physical specificity]
        return (
            f"{description}. {cam_desc}, {light_desc}, visible material texture, "
            "real surface imperfections, natural lens falloff, motivated shadows."
        )

if __name__ == "__main__":
    # Quick test logic
    import asyncio
    class MockBridge:
        async def direct(self, system_prompt, user_prompt):
            return '[{"subject": "Elara", "action": "walking", "environment": "neon city", "camera_preset": "tracking", "lighting_style": "neon"}]'

    async def test():
        gen = AssetPromptGenerator(MockBridge())
        scene = {"time": "Midnight", "visuals": "Neon rain", "action": "Walking through puddles"}
        bible = {"content": "Cyberpunk city"}
        results = await gen.generate_prompts_from_script({"scenes": [scene]}, bible)
        print(f"Generated {len(results)} prompts.")
        for r in results:
            print(f"- {r['base_prompt']}")

    asyncio.run(test())
