"""
Character Consistency Engine — Visual Identity Lock for Cinesmith.

Problem: FLUX/SD models generate different faces, clothing, and proportions
for the same character across shots.

Solution:
  1. Parse character visual fingerprints from the Lore Bible
  2. Inject full descriptors into EVERY shot prompt containing that character
  3. Seed-lock related shots to a character-specific seed family
  4. (Optional) Inject anchor images into FLUX Redux for pixel-level consistency

Usage:
    engine = CharacterConsistencyEngine("data/lore_bible/world_bible.md")
    enriched_prompt = engine.enrich_prompt(
        "Elara walks through a neon alley",
        detect_characters=True
    )
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

import logging

logger = logging.getLogger("CharacterConsistency")


class CharacterConsistencyEngine:
    """
    Manages visual character consistency across a production.

    Attributes:
        characters: dict of {name: {descriptor, appearance, seed_base, anchor_path}}
    """

    def __init__(
        self,
        lore_bible_path: str,
        anchor_dir: str = "data/character_banks/anchors",
    ):
        self.lore_bible_path = Path(lore_bible_path)
        self.anchor_dir = Path(anchor_dir)
        self.anchor_dir.mkdir(parents=True, exist_ok=True)

        self.characters: Dict[str, Dict[str, Any]] = {}
        if self.lore_bible_path.exists():
            self.characters = self._parse_lore_bible()
            logger.info(f"Parsed {len(self.characters)} character(s) from lore bible")
        else:
            logger.warning(f"Lore bible not found at {lore_bible_path}")

    # ------------------------------------------------------------------
    # Lore Bible Parsing
    # ------------------------------------------------------------------

    def _parse_lore_bible(self) -> Dict[str, Dict[str, Any]]:
        """
        Scans markdown lore bible for ## KEY CHARACTER: NAME sections.
        Extracts physical appearance, clothing, signature items.
        """
        text = self.lore_bible_path.read_text(encoding="utf-8")
        characters = {}

        # Split on "## KEY CHARACTER:" headers
        blocks = re.split(r'##\s*KEY\s*CHARACTER:\s*', text, flags=re.IGNORECASE)
        for block in blocks[1:]:
            lines = block.strip().splitlines()
            if not lines:
                continue

            name = lines[0].strip()
            block_text = "\n".join(lines[1:])

            appearance = self._extract_section(block_text, "Physical Appearance")
            clothing = self._extract_section(block_text, "Clothing")
            signature = self._extract_section(block_text, "Signature Item")
            role = self._extract_section(block_text, "Role")

            # Build compact descriptor string
            parts = []
            if appearance:
                parts.append(self._flatten_bullets(appearance))
            if clothing:
                parts.append(self._flatten_bullets(clothing))
            if signature:
                parts.append(self._flatten_bullets(signature))

            descriptor = "; ".join(parts)

            # Deterministic seed base from character name
            seed_base = int(hashlib.md5(name.encode()).hexdigest(), 16) % (2**31)

            # Anchor image path (supports .png, .jpg, .jpeg, .webp)
            safe_name = self._safe_filename(name)
            anchor_path = None
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                candidate = self.anchor_dir / f"{safe_name}{ext}"
                if candidate.exists():
                    anchor_path = candidate
                    break
            if anchor_path is None:
                anchor_path = self.anchor_dir / f"{safe_name}.png"

            characters[name.upper()] = {
                "name": name,
                "descriptor": descriptor,
                "role": self._flatten_bullets(role) if role else "",
                "seed_base": seed_base,
                "anchor_path": str(anchor_path),
                "has_anchor": anchor_path.exists(),
            }

        return characters

    @staticmethod
    def _extract_section(text: str, header: str) -> Optional[str]:
        """Extract bullet list under a markdown header like '**Physical Appearance:**'"""
        pattern = rf"\*\*{re.escape(header)}:\*\*\s*(.*?)(?=\n##|\n\*\*|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _flatten_bullets(text: str) -> str:
        """Convert markdown bullet list to semicolon-separated string."""
        lines = [line.strip().lstrip("-* ").strip() for line in text.splitlines() if line.strip()]
        return "; ".join(lines)

    @staticmethod
    def _safe_filename(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()

    # ------------------------------------------------------------------
    # Character Detection
    # ------------------------------------------------------------------

    def detect_characters(self, text: str) -> List[str]:
        """
        Detect which characters appear in a shot description.
        Matches on first name, last name, or full name.
        """
        text_upper = text.upper()
        found = []
        for char_key, info in self.characters.items():
            name = info["name"].upper()
            # Match full name or first name
            if name in text_upper:
                found.append(char_key)
            else:
                parts = name.split()
                for part in parts:
                    if len(part) > 2 and part in text_upper:
                        found.append(char_key)
                        break
        return list(dict.fromkeys(found))  # preserve order, dedupe

    # ------------------------------------------------------------------
    # Prompt Enrichment
    # ------------------------------------------------------------------

    def enrich_prompt(self, prompt: str, character_names: Optional[List[str]] = None, detect: bool = True) -> str:
        """
        Injects character visual fingerprints into a generation prompt.

        Example:
            Input:  "Elara walks through a neon alley"
            Output: "[CHARACTER: ELARA VANCE] Short asymmetrical undercut dyed
                     iridescent silver; cybernetic eyes with subtle gold iris ring;
                     heavy weathered tech-wear trench coat in matte charcoal with
                     glowing blue fiber-optic seams; holding vintage brass data reader.
                     [SCENE] Elara walks through a neon alley"
        """
        if character_names is None and detect:
            character_names = self.detect_characters(prompt)

        if not character_names:
            return prompt

        segments = []
        for char_key in character_names:
            info = self.characters.get(char_key)
            if not info:
                continue
            descriptor = info["descriptor"]
            if descriptor:
                segments.append(f"[CHARACTER: {info['name']}] {descriptor}")

        if not segments:
            return prompt

        enriched = " ".join(segments) + f" [SCENE] {prompt}"
        logger.info(f"Enriched prompt with {len(segments)} character segment(s)")
        return enriched

    # ------------------------------------------------------------------
    # Seed Management
    # ------------------------------------------------------------------

    def get_seed_for_shot(self, character_names: List[str], shot_index: int = 0) -> int:
        """
        Returns a deterministic seed for a shot.
        Combines character seed bases with shot index so related shots
        share genetic material but aren't identical.
        """
        if not character_names:
            return -1  # random

        seed = 0
        for name in character_names:
            info = self.characters.get(name.upper())
            if info:
                seed ^= info["seed_base"]
        seed = (seed + shot_index * 7919) % (2**31)  # 7919 is a large prime
        return seed

    # ------------------------------------------------------------------
    # Anchor Image Management
    # ------------------------------------------------------------------

    def needs_anchor(self, character_name: str) -> bool:
        return not self.characters.get(character_name.upper(), {}).get("has_anchor", False)

    def get_anchor_path(self, character_name: str) -> Optional[str]:
        return self.characters.get(character_name.upper(), {}).get("anchor_path")

    def register_anchor(self, character_name: str, image_path: str):
        """Call this after generating an anchor image to record it."""
        key = character_name.upper()
        if key in self.characters:
            self.characters[key]["has_anchor"] = True
            self.characters[key]["anchor_path"] = image_path
            logger.info(f"Anchor registered for {character_name}: {image_path}")

    def get_anchor_prompt(self, character_name: str) -> str:
        """Builds a dedicated anchor-generation prompt for a character."""
        info = self.characters.get(character_name.upper())
        if not info:
            return f"portrait of {character_name}, highly detailed"
        desc = info["descriptor"]
        return (
            f"Character reference portrait of {info['name']}. {desc}. "
            f"Full body visible, neutral pose, flat lighting, white background, "
            f"sharp focus on face and clothing details, photorealistic, 8k."
        )

    # ------------------------------------------------------------------
    # Redux Workflow Injection
    # ------------------------------------------------------------------

    def inject_redux_anchor(self, workflow: Dict[str, Any], character_name: str) -> Dict[str, Any]:
        """
        Injects a character anchor image into a FLUX Redux workflow.
        Looks for FluxReduxImageEncoder node and updates its image input.
        If no anchor exists, returns workflow unchanged.
        """
        anchor_path = self.get_anchor_path(character_name)
        if not anchor_path or not Path(anchor_path).exists():
            return workflow

        wf = json.loads(json.dumps(workflow))  # deep copy
        prompt_nodes = wf.get("prompt", wf)

        for node_id, node in prompt_nodes.items():
            if isinstance(node, dict) and node.get("class_type") == "FluxReduxImageEncoder":
                inputs = node.get("inputs", {})
                inputs["image"] = anchor_path
                logger.info(f"Injected Redux anchor for {character_name} into node {node_id}")
                break
        else:
            logger.debug(f"No FluxReduxImageEncoder node found; skipping Redux injection")

        return wf

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "characters": self.characters,
            "lore_bible": str(self.lore_bible_path),
            "anchor_dir": str(self.anchor_dir),
        }
