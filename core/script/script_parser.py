import re
from typing import List, Dict, Any

class ScriptParser:
    """
    Parses Markdown-based pilot scripts into structured data.
    Supports extraction of scenes, characters, locations, and audio cues.
    """

    def __init__(self):
        # Regex patterns for parsing the specific Markdown structure
        self.title_pattern = re.compile(r'^# SCRIPT:\s*(.*)', re.MULTILINE)
        self.scene_pattern = re.compile(r'^## SCENE \d+:\s*(.*)', re.MULTILINE)
        self.meta_pattern = re.compile(r'\*\*(.*?):\*\*\s*(.*)', re.MULTILINE)
        # Audio cues are expected to be list items starting with '-'
        self.audio_cue_pattern = re.compile(r'^- (.*)', re.MULTILINE)

    def parse(self, script_path: str) -> Dict[str, Any]:
        """
        Parses the markdown file at script_path into a structured dictionary.
        """
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Script file not found at {script_path}") from None

        parsed_data = {
            "title": "",
            "scenes": [],
            "character_registry": set(),
            "location_registry": set(),
            "full_text": content
        }

        # Extract Title
        title_match = self.title_pattern.search(content)
        if title_match:
            parsed_data["title"] = title_match.group(1).strip()

        # Split by scenes using the scene pattern
        scene_splits = list(self.scene_pattern.finditer(content))
        
        for i, match in enumerate(scene_splits):
            scene_start = match.start()
            scene_end = scene_splits[i+1].start() if i + 1 < len(scene_splits) else len(content)
            scene_text = content[scene_start:scene_end]
            
            scene_title = match.group(1).strip()
            scene_data = self._parse_scene_block(scene_title, scene_text)
            parsed_data["scenes"].append(scene_data)
            
            # Populate registries
            parsed_data["character_registry"].update(scene_data.get("characters", []))
            parsed_data["location_registry"].update(scene_data.get("locations", []))

        # Convert sets to lists for JSON-serializability if needed, 
        # but the requirement says dict, so we'll keep it clean.
        parsed_data["character_registry"] = sorted(list(parsed_data["character_registry"]))
        parsed_data["location_registry"] = sorted(list(parsed_data["location_registry"]))

        return parsed_data

    def _parse_scene_block(self, title: str, text: str) -> Dict[str, Any]:
        """
        Helper to parse an individual scene block.
        """
        scene = {
            "id": title, # Using title as ID for simplicity in this version
            "time": "Unknown",
            "characters": [],
            "locations": [],
            "props": [],
            "visual_notes": "",
            "action": "",
            "audio_cues": []
        }

        # Extracting specific sections via regex or simple keyword splitting
        # We look for patterns like **Time:**, **Visuals:**, **Action:**, **Audio:**
        
        # 1. Time/Meta extraction
        time_match = re.search(r'\*\*Time:\*\*\s*(.*)', text)
        if time_match:
            scene["time"] = time_match.group(1).strip()

        # 2. Visuals, Action, Audio blocks
        # We'll use a more robust approach by splitting the block into sections
        sections = {
            "visuals": re.search(r'\*\*Visuals:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', text, re.DOTALL),
            "action": re.search(r'\*\*Action:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', text, re.DOTALL),
            "audio": re.search(r'\*\*Audio:\*\*\s*(.*?)(?=\n\*\*|\n##|$)', text, re.DOTALL)
        }

        if sections["visuals"]:
            scene["visual_notes"] = sections["visuals"].group(1).strip()
        if sections["action"]:
            scene["action"] = sections["action"].group(1).strip()
        if sections["audio"]:
            audio_block = sections["audio"].group(1)
            # Improved regex to capture all lines starting with '-' within the audio block
            cues = re.findall(r'^\s*-\s*(.*)', audio_block, re.MULTILINE)
            scene["audio_cues"] = [cue.strip() for cue in cues]

        # 3. Extract Characters and Locations from text context
        # In a real production parser, this would use NLP or a more complex NER model.
        # For J10, we'll do basic extraction based on capitalized names or specific keywords.
        scene["characters"] = self._extract_entities(text, "character")
        scene["locations"] = self._extract_entities(text, "location")
        
        return scene

    def _extract_entities(self, text: str, entity_type: str) -> List[str]:
        """
        Placeholder for NER. For this task, we look for common patterns.
        In the demo script, Elara Vance is a character.
        """
        # Very simple heuristic: search for known names or capitalized words in specific contexts
        entities = []
        if entity_type == "character":
            # Looking for ELARA VANCE (all caps) or common patterns like Elara Vance
            found = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b|\b[A-Z]{2,}(?:\s[A-Z]{2,})*\b', text)
            # Filter out non-names (very crude for this hackathon implementation)
            blacklist = ["SCENE", "TIME", "VISUALS", "ACTION", "AUDIO", "MIDNIGHT", "CONTINUOUS"]
            for f in found:
                if f not in blacklist and f not in entities:
                    entities.append(f)
        elif entity_type == "location":
            # Extracting locations from scene titles if they match a pattern or are specifically noted
            # For now, we'll extract the scene title itself as a primary location indicator for simplicity
            loc_match = re.search(r'^## SCENE \d+: (.*)', text, re.MULTILINE)
            if loc_match:
                entities.append(loc_match.group(1).strip())

        return entities

    def extract_character_continuity_requirements(self, parsed: Dict[str, Any]) -> List[str]:
        """
        Derives consistency constraints for the Director Schema.
        Example: "Character [Name] must appear in [Scene IDs]"
        """
        requirements = []
        char_scene_map = {}

        for scene in parsed["scenes"]:
            for char in scene["characters"]:
                if char not in char_scene_map:
                    char_scene_map[char] = []
                char_scene_map[char].append(scene["id"])

        for char, scenes in char_scene_map.items():
            requirements.append(f"Character '{char}' consistency check for scenes: {', '.join(scenes)}")

        return requirements

if __name__ == "__main__":
    # Simple manual test if run directly
    parser = ScriptParser()
    try:
        data = parser.parse("./Desktop/cinesmith_v01/scripts/demo/pilot_script.md")
        print("Parsed Successfully!")
        print(f"Title: {data['title']}")
        print(f"Characters: {data['character_registry']}")
    except Exception as e:
        print(f"Error: {e}")
