import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from core.bridge.kimi_bridge import KimiBridge

logger = logging.getLogger(__name__)

class WorldBibleGenerator:
    """
    Transforms a single-line creative idea into a full World Bible
    using Kimi's 1M context window + pack_c_epistemic_deep_dive + pack_a_neural_aesthetic.
    """
    
    SYSTEM_PROMPT = """
    You are a world-builder and creative director. Given a single-line creative concept,
    generate a complete WORLD BIBLE that will serve as the authoritative reference document
    for an AI cinematic production system.

    Use the context frameworks provided to build depth, consistency, and cinematic precision.
    
    OUTPUT FORMAT — Return a markdown document with these exact sections:
    # WORLD BIBLE: {TITLE}
    ## SETTING: {World/Location Name}
    [2-3 paragraphs of setting description]
    ## VISUAL AESTHETIC (The 'Look')
    - Lighting: [precise cinematography description]
    - Color Palette: [4-6 hex codes with names]
    - Textures: [5+ specific material/environmental descriptors]
    ## KEY CHARACTER: {CHARACTER NAME}
    - Role: [narrative function]
    - Physical Appearance: [detailed, specific, consistent]
    - Signature Item: [props/accessories that identify them]
    ## CORE CONFLICT
    [The central dramatic tension — 1-2 paragraphs]
    ## TONE & GENRE MARKERS
    [5-10 reference points: films, photography, visual artists]
    ## CONSISTENCY ANCHORS (DO NOT VIOLATE)
    [5-10 specific visual rules that MUST hold across all generated assets]
    """

    def __init__(self, kimi_bridge: KimiBridge):
        self.kimi = kimi_bridge

    async def generate(self, one_line_idea: str, genre_hint: str = None) -> Dict[str, Any]:
        """
        Generates a complete world bible from a single idea.
        Injects context via the KimiBridge.
        """
        logger.info(f"Generating World Bible for idea: {one_line_idea}")
        
        # In a real implementation, we would fetch and inject the prompt libraries here.
        # For now, we construct the payload including the system instructions.
        
        prompt = f"Concept: {one_line_idea}\nGenre Hint: {genre_hint if genre_hint else 'Cinematic/Sci-Fi'}"
        
        # We call Kimi with the specialized system prompt
        response_text = await self.kimi.direct(
            system_prompt=self.SYSTEM_PROMPT,
            user_input=prompt
        )

        # Parse the markdown response into a structured dictionary
        parsed_data = self._parse_markdown_bible(response_text)
        
        return parsed_data

    def _parse_markdown_bible(self, md_content: str) -> Dict[str, Any]:
        """
        Heuristic parser to convert the Markdown Bible into structured data.
        """
        import re
        
        data = {
            "world_bible_text": md_content,
            "title": "",
            "setting": "",
            "visual_aesthetic": {},
            "character": {},
            "consistency_anchors": []
        }

        # Title extraction
        title_match = re.search(r'^# WORLD BIBLE:\s*(.*)', md_content, re.MULTILINE)
        if title_match:
            data["title"] = title_match.group(1).strip()

        # Setting extraction
        setting_match = re.search(r'## SETTING:\s*(.*?)(?=\n##|\n#|$)', md_content, re.DOTALL)
        if setting_match:
            data["setting"] = setting_match.group(1).strip()

        # Visual Aesthetic extraction (Lighting, Palette, Textures)
        aesthetic_block = re.search(r'## VISUAL AESTHETIC \(The \'Look\'\)(.*?)(?=\n##|$)', md_content, re.DOTALL)
        if aesthetic_block:
            block = aesthetic_block.group(1)
            lighting = re.search(r'- Lighting:\s*(.*)', block)
            palette = re.search(r'- Color Palette:\s*(.*)', block)
            textures = re.search(r'- Textures:\s*(.*)', block)
            
            if lighting: data["visual_aesthetic"]["lighting"] = lighting.group(1).strip()
            if palette: data["visual_aesthetic"]["palette"] = palette.group(1).strip()
            if textures: data["visual_aesthetic"]["textures"] = textures.group(1).strip()

        # Character extraction (Simplified)
        char_match = re.search(r'## KEY CHARACTER:\s*(.*?)\n', md_content)
        if char_match:
            data["character"]["name"] = char_match.group(1).strip()
            appearance = re.search(r'- Physical Appearance:\s*(.*)', md_content)
            if appearance: data["character"]["appearance"] = appearance.group(1).strip()

        # Consistency Anchors extraction
        anchors_match = re.search(r'## CONSISTENCY ANCHORS \(DO NOT VIOLATE\)(.*?)(?=\n##|\n#|$)', md_content, re.DOTALL)
        if anchors_match:
            anchor_text = anchors_match.group(1).strip()
            anchors = re.findall(r'-\s*(.*)', anchor_text)
            data["consistency_anchors"] = [a.strip() for a in anchors]

        return data

    async def refine(self, world_bible: str, feedback: str) -> str:
        """
        Iterative refinement — takes existing world bible + feedback,
        returns improved version.
        """
        logger.info("Refining World Bible with user feedback.")
        refine_prompt = f"Existing World Bible:\n{world_bible}\n\nUser Feedback/Requested Changes: {feedback}\n\nPlease provide the updated, complete World Bible following the same structure."
        
        return await self.kimi.direct(
            system_prompt=self.SYSTEM_PROMPT,
            user_input=refine_prompt
        )

if __name__ == "__main__":
    # Quick manual test logic
    import asyncio
    from core.bridge.kimi_bridge import KimiBridge