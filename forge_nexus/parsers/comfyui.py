from pathlib import Path
import json
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class WorkNode:
    node_id: str
    class_type: str
    category: str  # Loader, Sampler, Conditioning, VAE, Output, Utility
    inputs: Dict[str, Any]
    outputs: List[str]
    position: List[int]

@dataclass
class WorkEdge:
    from_node: str
    to_node: str
    from_output: int
    to_input: str
    edge_type: str = "CONNECTS"

@dataclass
class WorkflowManifest:
    id: str
    type: str = "Workflow"
    source_file: str = ""
    content_hash: str = ""
    metadata: Dict = field(default_factory=dict)
    nodes: List[Dict] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    referenced_prompts: List[str] = field(default_factory=list)
    referenced_models: List[str] = field(default_factory=list)
    referenced_characters: List[str] = field(default_factory=list)

class ComfyUIParser:
    NODE_CATEGORIES = {
        "CheckpointLoaderSimple": "Loader",
        "UNETLoader": "Loader",
        "VAELoader": "Loader",
        "CLIPLoader": "Loader",
        "KSampler": "Sampler",
        "KSamplerAdvanced": "Sampler",
        "CLIPTextEncode": "Conditioning",
        "CLIPSetLastLayer": "Conditioning",
        "VAEDecode": "VAE",
        "VAEEncode": "VAE",
        "SaveImage": "Output",
        "PreviewImage": "Output",
        "LoadImage": "Loader",
        "ImageScale": "Utility",
        "FaceDetailer": "PostProcess",
    }
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
    
    def parse(self, workflow_path: Path) -> WorkflowManifest:
        raw = json.loads(workflow_path.read_text())
        
        # Compute hash for stale detection
        content_hash = hashlib.sha256(workflow_path.read_bytes()).hexdigest()[:16]
        
        nodes = []
        edges = []
        entry_points = []
        outputs = []
        referenced_models = []
        
        # Parse nodes
        for node_id, node_data in raw.items():
            class_type = node_data.get("class_type", "Unknown")
            category = self.NODE_CATEGORIES.get(class_type, "Unknown")
            
            # Detect model references
            if class_type in ("CheckpointLoaderSimple", "UNETLoader"):
                model_name = node_data.get("inputs", {}).get("ckpt_name", "")
                if model_name:
                    referenced_models.append(model_name)
            
            # Detect entry points (no incoming connections)
            has_incoming = False
            for other_id, other_data in raw.items():
                inputs = other_data.get("inputs", {})
                for val in inputs.values():
                    if isinstance(val, list) and len(val) == 2 and str(val[0]) == str(node_id):
                        has_incoming = True
                        break
                if has_incoming: break

            if not has_incoming and category == "Loader":
                entry_points.append(node_id)
            
            # Detect outputs
            if category == "Output":
                outputs.append(node_id)
            
            nodes.append({
                "node_id": node_id,
                "class_type": class_type,
                "category": category,
                "inputs": node_data.get("inputs", {}),
                "outputs": self._infer_outputs(node_data),
                "position": node_data.get("pos", [0, 0])
            })
        
        # Parse edges
        for node_id, node_data in raw.items():
            for input_name, input_val in node_data.get("inputs", {}).items():
                if isinstance(input_val, list) and len(input_val) == 2:
                    edges.append({
                        "from": str(input_val[0]),
                        "to": node_id,
                        "from_output": input_val[1],
                        "to_input": input_name,
                        "type": "CONNECTS"
                    })
        
        # Extract prompt references from CLIPTextEncode nodes
        referenced_prompts = []
        for node in nodes:
            if node["class_type"] == "CLIPTextEncode":
                text_input = node["inputs"].get("text", "")
                if isinstance(text_input, str):
                    # Look for {{prompt.name}} or prompt file references
                    referenced_prompts.extend(self._extract_prompt_refs(text_input))
        
        manifest = WorkflowManifest(
            id=f"wf_{workflow_path.stem}",
            source_file=str(workflow_path.relative_to(self.project_path)),
            content_hash=content_hash,
            metadata={
                "comfyui_version": "unknown",
                "node_count": len(nodes),
                "total_edges": len(edges)
            },
            nodes=nodes,
            edges=edges,
            entry_points=entry_points,
            outputs=outputs,
            referenced_prompts=list(set(referenced_prompts)),
            referenced_models=list(set(referenced_models)),
            referenced_characters=[]  # Populated by cross-reference pass
        )
        
        return manifest
    
    def _infer_outputs(self, node_data: dict) -> List[str]:
        type_map = {
            "CheckpointLoaderSimple": ["MODEL", "CLIP", "VAE"],
            "KSampler": ["LATENT"],
            "CLIPTextEncode": ["CONDITIONING"],
            "VAEDecode": ["IMAGE"],
            "SaveImage": [],
        }
        return type_map.get(node_data.get("class_type"), ["UNKNOWN"])
    
    def _extract_prompt_refs(self, text: str) -> List[str]:
        import re
        refs = re.findall(r'\{\{prompt\.(\w+)\}\}', text)
        return refs
