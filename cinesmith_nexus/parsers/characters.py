import yaml
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

@dataclass
class CharacterManifest:
    id: str
    type: str = "Character"
    source_file: str = ""
    content_hash: str = ""
    name: str = ""
    attributes: dict = field(default_factory=dict)
    consistency_rules: dict = field(default_factory=dict)
    referenced_by: dict = field(default_factory=lambda: {
        "workflows": [], "scenes": [], "assets": []
    })
    linked_prompts: List[str] = field(default_factory=list)

class CharacterParser:
    def __init__(self, project_path: Path):
        self.project_path = project_path
    
    def parse(self, char_path: Path) -> CharacterManifest:
        data = yaml.safe_load(char_path.read_text())
        content_hash = hashlib.sha256(char_path.read_bytes()).hexdigest()[:16]
        
        manifest = CharacterManifest(
            id=f"char_{char_path.stem}",
            source_file=str(char_path.relative_to(self.project_path)),
            content_hash=content_hash,
            name=data.get("name", char_path.stem),
            attributes=data.get("attributes", {}),
            consistency_rules=data.get("consistency", {}),
            referenced_by={
                "workflows": data.get("workflows", []),
                "scenes": data.get("scenes", []),
                "assets": data.get("assets", [])
            },
            linked_prompts=data.get("prompts", [])
        )
        
        return manifest
