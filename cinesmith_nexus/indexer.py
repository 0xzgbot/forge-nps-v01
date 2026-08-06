from pathlib import Path
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any

# Import parsers - relative imports used assuming indexer is run as part of the package
try:
    from cinesmith_nexus.parsers.comfyui import ComfyUIParser
    from cinesmith_nexus.parsers.prompts import PromptParser
    from cinesmith_nexus.parsers.characters import CharacterParser
except ImportError:
    # Fallback for direct execution if path not in PYTHONPATH
    from parsers.comfyui import ComfyUIParser
    from parsers.prompts import PromptParser
    from parsers.characters import CharacterParser

class ManifestIndexer:
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.manifest_dir = self.project_path / ".cinesmith-nexus" / "manifests"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        
        self.workflow_parser = ComfyUIParser(self.project_path)
        self.prompt_parser = PromptParser(self.project_path)
        self.character_parser = CharacterParser(self.project_path)
    
    def index(self):
        """Phase 1: Generate all manifests."""
        manifests = {
            "project": {
                "name": self.project_path.name,
                "path": str(self.project_path),
                "indexed_at": datetime.now().isoformat(),
                "manifest_version": "1.0"
            },
            "manifests": {
                "workflows": [],
                "characters": [],
                "prompts": []
            }
        }
        
        # Index workflows
        workflow_dir = self.project_path / "workflows"
        if workflow_dir.exists():
            for wf_file in workflow_dir.glob("*.json"):
                manifest = self.workflow_parser.parse(wf_file)
                self._save_manifest("workflows", manifest)
                manifests["manifests"]["workflows"].append({
                    "id": manifest.id,
                    "file": str(wf_file.relative_to(self.project_path)),
                    "manifest": f"workflows/{wf_file.stem}.json"
                })
        
        # Index characters
        char_dir = self.project_path / "characters"
        if char_dir.exists():
            for char_file in char_dir.glob("*.yaml"):
                manifest = self.character_parser.parse(char_file)
                self._save_manifest("characters", manifest)
                manifests["manifests"]["characters"].append({
                    "id": manifest.id,
                    "file": str(char_file.relative_to(self.project_path)),
                    "manifest": f"characters/{char_file.stem}.json"
                })
        
        # Index prompts
        prompt_dir = self.project_path / "prompts"
        if prompt_dir.exists():
            for prompt_file in prompt_dir.glob("*.md"):
                manifest = self.prompt_parser.parse(prompt_file)
                self._save_manifest("prompts", manifest)
                manifests["manifests"]["prompts"].append({
                    "id": manifest.id,
                    "file": str(prompt_file.relative_to(self.project_path)),
                    "manifest": f"prompts/{prompt_file.stem}.json"
                })
        
        # Cross-reference pass: link workflows to characters/prompts
        self._cross_reference(manifests)
        
        # Save project registry
        (self.manifest_dir / "project.json").write_text(
            json.dumps(manifests, indent=2, default=str)
        )
        
        return manifests
    
    def _save_manifest(self, category: str, manifest):
        out_dir = self.manifest_dir / category
        out_dir.mkdir(exist_ok=True)
        
        # Determine the stem based on the ID (e.g., wf_cybernoir -> cybernoir)
        parts = manifest.id.split('_', 1)
        stem = parts[1] if len(parts) > 1 else parts[0]
        
        out_path = out_dir / f"{stem}.json"
        # Convert dataclass to dict if necessary
        data = manifest.__dict__ if hasattr(manifest, '__dict__') else manifest
        out_path.write_text(json.dumps(data, indent=2, default=str))
    
    def _cross_reference(self, registry: dict):
        """Link manifests to each other based on IDs."""
        # Load all manifests into memory for cross-referencing
        workflow_manifests = {}
        for wf in registry["manifests"]["workflows"]:
            path = self.manifest_dir / wf["manifest"]
            if path.exists():
                workflow_manifests[wf["id"]] = json.loads(path.read_text())
        
        # For each workflow, resolve referenced_prompts to actual prompt IDs
        for wf_id, wf_data in workflow_manifests.items():
            resolved_prompts = []
            for prompt_ref in wf_data.get("referenced_prompts", []):
                # Match by prompt name or ID
                for p in registry["manifests"]["prompts"]:
                    if prompt_ref in p["id"] or prompt_ref in p["file"]:
                        resolved_prompts.append(p["id"])
                        break
            wf_data["referenced_prompts"] = resolved_prompts
            
            # Save updated manifest back to disk
            stem = wf_data["id"].split('_', 1)[1] if '_' in wf_data["id"] else wf_data["id"]
            out_path = self.manifest_dir / "workflows" / f"{stem}.json"
            if out_path.exists():
                out_path.write_text(json.dumps(wf_data, indent=2, default=str))

if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    indexer = ManifestIndexer(p)
    print("Starting indexing...")
    res = indexer.index()
    print(f"Indexing complete. Processed {len(res['manifests']['workflows'])} workflows, "
          f"{len(res['manifests']['characters'])} characters, and "
          f"{len(res['manifests']['prompts'])} prompts.")
