"""
CharacterAnchorManager — extracts character names from shot descriptions,
loads matching anchor images, and wires them into Kimi-VL audits.
"""
import re
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("CharacterAnchorManager")

# Default anchor directory relative to project root
_DEFAULT_ANCHORS_DIR = Path(__file__).parents[2] / "data" / "character_banks" / "anchors"

# Common character name patterns in shot descriptions
# Matches: "Character Elena", "Elena (protagonist)", "the hero Elena", "Elena and Marcus"
_NAME_PATTERNS = [
    # "Character <Name>" or "character <Name>" (case-insensitive prefix)
    r"(?i:character\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # "<Name> and <Name>" patterns
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:and|with|alongside|next\s+to|beside)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # "<Name> (role)" patterns
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\([^)]*\)",
    # Standalone capitalized multi-word names (exactly 2 words, to avoid false positives)
    r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b",
]

# Words that are NOT character names (common false positives)
_FALSE_POSITIVES = {
    "The", "Shot", "Camera", "Wide", "Close", "Medium", "Low", "High",
    "Golden", "Magic", "Natural", "Soft", "Hard", "Warm", "Cool",
    "Cinematic", "Film", "Movie", "Scene", "Action", "Light", "Dark",
    "Background", "Foreground", "Subject", "Character", "Protagonist",
    "Antagonist", "Hero", "Villain", "Main", "Primary", "Secondary",
    "Over", "Under", "Above", "Below", "Behind", "In", "On", "At",
    "By", "From", "With", "Without", "Through", "Across", "Around",
    "During", "After", "Before", "While", "When", "Where", "How",
    "What", "Which", "That", "This", "These", "Those", "Such",
    "Very", "Quite", "Rather", "Fairly", "Pretty", "Really", "Truly",
    "Just", "Only", "Even", "Also", "Too", "Both", "Either", "Neither",
    "Each", "Every", "All", "Any", "Some", "No", "Not", "Never",
    "Always", "Often", "Sometimes", "Usually", "Generally", "Normally",
    "Specifically", "Particularly", "Especially", "Indeed", "Certainly",
    "Obviously", "Clearly", "Apparently", "Seemingly", "Presumably",
    "Probably", "Possibly", "Perhaps", "Maybe", "Perhaps", "Likely",
    "Unlikely", "Surely", "Definitely", "Absolutely", "Completely",
    "Totally", "Entirely", "Wholly", "Fully", "Perfectly", "Exactly",
    "Precisely", "Accurately", "Correctly", "Rightly", "Properly",
    "Appropriately", "Suitably", "Fittingly", "Suitably", "Well",
    "Good", "Bad", "Great", "Excellent", "Amazing", "Wonderful",
    "Beautiful", "Gorgeous", "Stunning", "Breathtaking", "Magnificent",
    "Splendid", "Superb", "Fantastic", "Fabulous", "Terrific",
    "Outstanding", "Remarkable", "Extraordinary", "Exceptional",
    "Incredible", "Unbelievable", "Amazing", "Astounding", "Astonishing",
    "Startling", "Shocking", "Surprising", "Unexpected", "Unforeseen",
    "Unanticipated", "Unpredicted", "Unimagined", "Unthought",
    "Unconceived", "Unenvisioned", "Unpictured", "Undreamed",
}


class CharacterAnchorManager:
    """
    Manages character anchor images for visual consistency auditing.

    Features:
    - Extract character names from shot descriptions
    - Load matching anchor images from character banks
    - Warn when anchors are missing and suggest generation
    - Wire anchors into Kimi-VL audit reference images
    """

    def __init__(self, anchors_dir: Optional[Path] = None):
        self.anchors_dir = Path(anchors_dir) if anchors_dir else _DEFAULT_ANCHORS_DIR
        self._known_characters: Dict[str, Path] = {}
        self._scan_anchors()

    def _scan_anchors(self):
        """Scan the anchors directory and build a lookup of known characters."""
        if not self.anchors_dir.exists():
            logger.info(f"[ANCHORS] Anchors directory does not exist yet: {self.anchors_dir}")
            return

        for anchor_file in self.anchors_dir.iterdir():
            if anchor_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                # Character name is the filename without extension
                char_name = anchor_file.stem
                self._known_characters[char_name.lower()] = anchor_file
                logger.debug(f"[ANCHORS] Loaded anchor: {char_name} -> {anchor_file}")

        logger.info(f"[ANCHORS] Scanned {len(self._known_characters)} known character anchors")

    def extract_characters(self, text: str) -> List[str]:
        """
        Extract character names from a shot description or prompt.

        Strategy:
        1. Match explicit "Character <Name>" patterns (case-insensitive prefix)
        2. Match "<Name> and <Name>" patterns
        3. Match "<Name> (role)" patterns
        4. Match standalone capitalized multi-word names
        5. Filter out false positives (common words, single letters, etc.)
        """
        if not text:
            return []

        names = set()

        # Pattern 1: "Character <Name>" or "character <Name>" (case-insensitive prefix)
        for match in re.finditer(r"(?i:character)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text):
            names.add(match.group(1))

        # Pattern 2: "<Name> and <Name>" patterns
        for match in re.finditer(
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:and|with|alongside|next\s+to|beside)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
            text
        ):
            names.add(match.group(1))
            names.add(match.group(2))

        # Pattern 3: "<Name> (role)" patterns
        for match in re.finditer(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+\([^)]*\)", text):
            names.add(match.group(1))

        # Pattern 4: Standalone capitalized multi-word names
        for match in re.finditer(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", text):
            names.add(match.group(1))

        # Filter out false positives
        filtered = set()
        for name in names:
            # Skip if any word in the name is a false positive
            words = name.split()
            if any(w in _FALSE_POSITIVES for w in words):
                continue
            # Skip single-word names (too ambiguous)
            if len(words) < 2:
                continue
            # Skip if the name is too short
            if len(name) < 4:
                continue
            filtered.add(name)

        result = sorted(filtered)
        if result:
            logger.debug(f"[ANCHORS] Extracted characters from '{text[:80]}...': {result}")

        return result

    def load_anchors(self, character_names: List[str]) -> List[Tuple[str, Path]]:
        """
        Load anchor images for the given character names.

        Returns:
            List of (character_name, anchor_path) tuples for characters with anchors.
        """
        anchors = []
        missing = []

        for char_name in character_names:
            # Try exact match first (case-insensitive)
            key = char_name.lower().replace(" ", "_")
            anchor_path = self._known_characters.get(key)

            if not anchor_path:
                # Try with spaces instead of underscores
                key = char_name.lower().replace("_", " ")
                anchor_path = self._known_characters.get(key)

            if not anchor_path:
                # Try direct file lookup
                for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    candidate = self.anchors_dir / f"{key}{ext}"
                    if candidate.exists():
                        anchor_path = candidate
                        break

            if anchor_path and anchor_path.exists():
                anchors.append((char_name, anchor_path))
            else:
                missing.append(char_name)

        # Log warnings for missing anchors
        if missing:
            for name in missing:
                logger.warning(
                    f"[ANCHORS] No anchor image found for character '{name}'. "
                    f"Search path: {self.anchors_dir}/"
                    f"{name.lower().replace(' ', '_')}.{{jpg,png}}. "
                    f"Suggestion: Use POST /api/characters/generate-anchor to create one."
                )

        return anchors

    def get_audit_references(self, shot_description: str) -> Dict[str, any]:
        """
        Main entry point: extract characters from shot description and load anchors.

        Returns:
            {
                "characters": ["Elara Vance", "Marcus Cole"],
                "anchors": [("Elara Vance", Path(...)), ...],
                "missing": ["Marcus Cole"],
                "reference_paths": [Path(...), ...],
                "warnings": ["No anchor for Marcus Cole", ...]
            }
        """
        characters = self.extract_characters(shot_description)
        anchors = self.load_anchors(characters)
        anchored_names = {name for name, _ in anchors}
        missing = [c for c in characters if c not in anchored_names]

        warnings = []
        for name in missing:
            warnings.append(
                f"No anchor image for '{name}' — VL audit will skip character comparison. "
                f"Generate one via POST /api/characters/generate-anchor"
            )

        return {
            "characters": characters,
            "anchors": anchors,
            "missing": missing,
            "reference_paths": [path for _, path in anchors],
            "warnings": warnings,
        }

    def has_anchor(self, character_name: str) -> bool:
        """Check if an anchor exists for a character."""
        key = character_name.lower().replace(" ", "_")
        return key in self._known_characters

    def list_known_characters(self) -> List[Dict[str, str]]:
        """List all known characters with their anchor paths."""
        return [
            {
                "name": name.replace("_", " ").title(),
                "anchor_path": str(path),
                "file_size": f"{path.stat().st_size / 1024:.1f}KB" if path.exists() else "N/A",
            }
            for name, path in self._known_characters.items()
        ]
