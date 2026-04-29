import json
from pathlib import Path
from typing import Dict, Any, Optional

class LibraryLoader:
    def __init__(self, library_dir: str):
        self.library_dir = Path(library_dir)

    def load_all(self):
        libraries = []
        if not self.library_dir.exists():
            print(f"Error: Directory {self.library_dir} does not exist.")
            return libraries

        for file_path in self.library_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    libraries.append(data)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
        return libraries

    def get_prompt(self, prompt_id: str, cinematic_params: Optional[Dict[str, Any]] = None, cinematic_engine=None) -> Dict[str, Any]:
        """
        Retrieves a base prompt and optionally enhances it using the CinematicEngine.
        """
        # For this implementation, we'll simulate finding a prompt by ID in the loaded libraries
        libraries = self.load_all()
        target_prompt = None

        for lib in libraries:
            if lib.get("id") == prompt_id or lib.get("title") == prompt_id:
                # The library might have 'entries' or just be a list of prompts
                entries = lib.get("entries", [])
                if entries:
                    target_prompt = entries[0]
                else:
                    target_prompt = lib
                break

        if not target_prompt:
            raise ValueError(f"Prompt with ID/Title '{prompt_id}' not found.")

        # Extract base text (handles if target_prompt is a string or dict)
        # Checking 'base_prompt' or 'text' as per common patterns in the JSON files
        if isinstance(target_prompt, dict):
            base_text = target_prompt.get("base_prompt") or target_prompt.get("text") or str(target_prompt)
            kernel = target_prompt.get("model_kernel", {})
        else:
            base_text = str(target_prompt)
            kernel = {}
        
        result = {
            "base_prompt": base_text,
            "kernel": kernel
        }

        if cinematic_params and cinematic_engine:
            enhanced_text = cinematic_engine.enhance(base_text, cinematic_params)
            result["enhanced_prompt"] = enhanced_text
        else:
            result["enhanced_prompt"] = base_text

        return result

if __name__ == "__main__":
    # Test the loader with the newly created files
    default_library_dir = Path(__file__).resolve().parents[2] / "data" / "prompt_libraries"
    loader = LibraryLoader(str(default_library_dir))
    libs = loader.load_all()
    print(f"Loaded {len(libs)} libraries.")
    for lib in libs:
        print(f"- {lib.get('title', 'Untitled')} (ID: {lib.get('id')})")
