import logging
import re
from typing import Dict, Any
from core.bridge.kimi_bridge import KimiBridge

logger = logging.getLogger(__name__)

class ScriptGenerator:
    """
    Generates a pilot script grounded in the World Bible.
    Uses the world bible as authoritative context (no contradictions allowed).
    Outputs in the exact format that ScriptParser (J10) can parse.
    """

    SYSTEM_PROMPT = """
    You are a cinematic screenwriter. Given a World Bible, write a PILOT SCRIPT
    for a short cinematic sequence (2-4 scenes, ~3 minutes of screen time).
    
    RULES:
    1. Every visual detail MUST reference specific elements from the World Bible
    2. Each scene must have clear visual + audio directives (used by AI generation)
    3. Character descriptions must match the World Bible EXACTLY
    4. Lighting must reference the established color palette
    5. OUTPUT FORMAT — Return a markdown document with these exact headers:

    # SCRIPT: {TITLE} — "{EPISODE TITLE}" (Pilot Sequence)

    ## SCENE 1: {SCENE TITLE}
    **Time:** [time of day]
    **Visuals:** [paragraph — cinematic visual description]
    **Action:** [paragraph — character actions]
    **Audio:**
    - [specific sound element 1]
    - [specific sound element 2]

    (Repeat for subsequent scenes)
    """

    def __init__(self, kimi_bridge: KimiBridge):
        self.kimi = kimi_bridge

    async def generate(self, world_bible: Dict[str, Any], num_scenes: int = 2) -> Dict[str, Any]:
        """
        Generates pilot script from world bible output.
        world_bible: output dict from WorldBibleGenerator.generate()
        Returns: {script_text: str, scenes: list[dict], character_appearances: dict}
        """
        logger.info(f"Generating Pilot Script for Bible: {world_bible.get('title', 'Untitled')}")

        # Construct the context from the bible dictionary
        context = f"""
        WORLD BIBLE CONTEXT:
        Title: {world_bible.get('title')}
        Setting: {world_bible.get('setting')}
        Visual Aesthetic: {json.dumps(world_bible.get('visual_aesthetic', {}))}
        Character Info: {json.dumps(world_bible.get('character', {}))}
        Consistency Anchors: {", ".join(world_bible.get('consistency_anchors', []))}
        """

        user_prompt = f"""
        Please write a {num_scenes}-scene pilot script based on the following World Bible.
        Ensure all characters and visual styles are strictly consistent with the bible.

        {context}
        """

        script_md = await self.kimi.direct(
            system_prompt=self.SYSTEM_PROMPT,
            user_input=user_prompt
        )

        # Use a simplified internal parser for the immediate return structure
        parsed_result = self._parse_script_markdown(script_md)
        
        return {
            "script_text": script_md,
            **parsed_result
        }

    def _parse_script_markdown(self, md_content: str) -> Dict[str, Any]:
        """
        Parses the generated markdown into a structured dict for the engine.
        Uses regex to identify scenes and their metadata blocks.
        """
        
        scenes = []
        # Split by scene headers: ## SCENE 1: ...
        scene_splits = list(re.finditer(r'## SCENE \d+:\s*(.*)', md_content))

        for i, match in enumerate(scene_splits):
            scene_start = match.start()
            scene_end = scene_splits[i+1].start() if i + 1 < len(scene_splits) else len(md_content)
            scene_block = md_content[scene_start:scene_end]
            
            title = match.group(1).strip()
            
            # Extract sub-blocks within the scene
            time_match = re.search(r'\*\*Time:\*\*\s*(.*)', scene_block)
            visuals_match = re.search(r'\*\*Visuals:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', scene_block, re.DOTALL)
            action_match = re.search(r'\*\*Action:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', scene_block, re.DOTALL)
            audio_match = re.search(r'\*\*Audio:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', scene_block, re.DOTALL)

            audio_cues = []
            if audio_match:
                audio_text = audio_match.group(1)
                audio_cues = [cue.strip().lstrip('- ').lstrip('* ') for cue in audio_text.split('\n') if cue.strip()]

            scene_data = {
                "id": title,
                "time": time_match.group(1).strip() if time_match else "Unknown",
                "visual_notes": visuals_match.group(1).strip() if visuals_match else "",
                "action": action_match.group(1).strip() if action_match else "",
                "audio_cues": audio_cues
            }
            scenes.append(scene_data)

        return {
            "scenes": scenes,
            "character_appearances": {} # Placeholder for character mapping logic
        }

import json # Needed for the context construction inside generate()
