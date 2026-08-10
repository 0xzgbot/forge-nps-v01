import re
import yaml
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

@dataclass
class PromptManifest:
    id: str
    type: str = "Prompt"
    source_file: str = ""
    content_hash: str = ""
    prompt_type: str = "positive"  # positive, negative, style
    content: str = ""
    frontmatter: dict = field(default_factory=dict)
    inheritance_chain: List[str] = field(default_factory=list)
    referenced_constants: List[dict] = field(default_factory=list)
    used_by: dict = field(default_factory=lambda: {"workflows": [], "characters": []})
    semantic_tags: List[str] = field(default_factory=list)

class PromptParser:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.constants_registry = self._load_constants()
    
    def parse(self, prompt_path: Path) -> PromptManifest:
        text = prompt_path.read_text()
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        
        # Extract YAML frontmatter
        frontmatter = {}
        content = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    content = parts[2].strip()
                except yaml.YAMLError:
                    pass
        
        # Determine prompt type from filename or frontmatter
        prompt_type = frontmatter.get("type", self._infer_type(prompt_path.name))
        
        # Extract constant references {{category.name}}
        constants = []
        for match in re.finditer(r'\{\{(\w+)\.(\w+)\}\}', content):
            cat, name = match.groups()
            constants.append({
                "name": name,
                "category": cat,
                "value": self.constants_registry.get(f"{cat}.{name}", "unknown")
            })
        
        # Build inheritance chain
        inheritance = []
        current = frontmatter.get("inherits")
        visited = set()
        while current and current not in visited:
            visited.add(current)
            inheritance.append(current)
            # Try to load parent frontmatter
            parent_path = self.project_path / "prompts" / current
            if parent_path.exists():
                try:
                    parent_text = parent_path.read_text()
                    if parent_text.startswith("---"):
                        parts = parent_text.split("---", 2)
                        if len(parts) >= 3:
                            parent_fm = yaml.safe_load(parts[1]) or {}
                            current = parent_fm.get("inherits")
                        else:
                            current = None
                    else:
                        current = None
                except Exception:
                    current = None
            else:
                break
        
        manifest = PromptManifest(
            id=f"prompt_{prompt_path.stem}",
            source_file=str(prompt_path.relative_to(self.project_path)),
            content_hash=content_hash,
            prompt_type=prompt_type,
            content=content[:500],  # Truncate for manifest
            frontmatter=frontmatter,
            inheritance_chain=inheritance,
            referenced_constants=constants,
            used_by={"workflows": [], "characters": []},  # Populated by cross-ref pass
            semantic_tags=frontmatter.get("tags", [])
        )
        
        return manifest
    
    def _infer_type(self, filename: str) -> str:
        fn = filename.lower()
        if "negative" in fn:
            return "negative"
        elif "style" in fn:
            return "style"
        return "positive"
    
    def _load_constants(self) -> dict:
        constants_file = self.project_path / "constants.yaml"
        if constants_file.exists():
            try:
                data = yaml.safe_load(constants_file.read_text())
                flat = {}
                for cat, items in data.items():
                    if isinstance(items, dict):
                        for name, val in items.items():
                            flat[f"{cat}.{name}"] = val
                return flat
            except Exception:
                return {}
        return {}
