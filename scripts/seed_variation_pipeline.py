#!/usr/bin/env python3
"""
Seed Image → Batch Variation Pipeline for Cinesmith.

Drop 1-2 seed/reference images into data/seed_images/.
This script generates 20-30 FLUX2 NVFP4 Turbo renders with systematic
variations in pose, angle, clothes, weather, and lighting.

Usage:
    # Basic: generate 24 variations from lore bible character + seed images
    python scripts/seed_variation_pipeline.py \
        --seed-images data/seed_images/elara_seed_01.png \
        --character "Elara Vance" \
        --count 24

    # With ComfyUI workflow template
    python scripts/seed_variation_pipeline.py \
        --seed-images data/seed_images/*.png \
        --workflow workflows/flux2_variation_api.json \
        --output data/seed_outputs/elara_variations \
        --count 30

    # Dry-run: print prompts without submitting
    python scripts/seed_variation_pipeline.py --dry-run --count 10
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Ensure repo root is importable
REPO_ROOT = Path(__file__).parent.parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.consistency.character_consistency_engine import CharacterConsistencyEngine


# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_COMFY_HOST = "http://localhost:8188"
DEFAULT_WORKFLOW = REPO_ROOT / "workflows" / "z_image_turbo_api.json"
SEED_IMAGES_DIR = REPO_ROOT / "data" / "seed_images"
OUTPUT_DIR = REPO_ROOT / "data" / "seed_outputs"
LORE_BIBLE = REPO_ROOT / "data" / "lore_bible" / "world_bible.md"
BANKS_DIR = REPO_ROOT / "data" / "character_banks"

QUALITY_CONSTANTS = "photorealism, hyperrealistic, sharp focus, professional photography, high detail, 8k resolution, cinema lens"


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class VariationTemplate:
    """One dimension of variation (e.g. pose, lighting, weather)."""
    name: str
    options: List[str]
    weight: float = 1.0  # relative probability of being applied


@dataclass
class VariationRecipe:
    """A fully-specified prompt variation ready to render."""
    index: int
    seed: int
    pose: str
    view: str
    lighting: str
    background: str
    extras: str
    crop: str
    prompt: str
    filename: str
    seed_image: Optional[Path] = None


# ─── Variation Engine ────────────────────────────────────────────────────────

class VariationEngine:
    """
    Generates systematic prompt variations from character DNA or product specifications.

    Uses the existing bank files (pose, view, lighting, background, extras, crop)
    and the Character Consistency Engine to lock character descriptors for characters.
    For products, it uses specialized dimension banks (angle, material, context, lighting).
    """

    def __init__(
        self,
        mode: str = "character",
        character_name: Optional[str] = None,
        product_description: Optional[str] = None,
        lore_bible_path: Optional[Path] = None,
        banks_dir: Optional[Path] = None,
        quality_constants: str = QUALITY_CONSTANTS,
        base_prompt: Optional[str] = None,
    ):
        self.mode = mode.lower()
        self.character_name = character_name
        self.product_description = product_description
        self.quality_constants = quality_constants
        self.cce = None
        self.char_descriptor = base_prompt or ""
        self.anchor_seed = 0

        # Load Character Consistency Engine if lore bible available and in character mode
        if self.mode == "character" and lore_bible_path and lore_bible_path.exists():
            try:
                self.cce = CharacterConsistencyEngine(str(lore_bible_path))
                if character_name and not base_prompt:
                    detected = self.cce.detect_characters(character_name)
                    if detected:
                        self.char_descriptor = self.cce.get_anchor_prompt(detected[0])
                        self.anchor_seed = hash(detected[0]) % (2**32)
                elif base_prompt:
                    self.anchor_seed = hash(base_prompt) % (2**32)
            except Exception as e:
                print(f"[WARN] CCE load failed: {e}. Running without character DNA.")
        elif base_prompt:
            self.anchor_seed = hash(base_prompt) % (2**32)

        # Load variation banks
        self.banks_dir = banks_dir or BANKS_DIR
        self.banks = self._load_banks()

    def _load_banks(self) -> Dict[str, List[str]]:
        banks = {}
        # Determine which bank directory to use
        target_dir = self.banks_dir
        if self.mode == "product":
            target_dir = self.banks_dir / "product_banks"

        if not target_dir.exists():
            print(f"[WARN] Bank directory {target_dir} not found.")
            return {}

        for bank_file in sorted(target_dir.glob("*_bank.txt")):
            name = bank_file.stem.replace("_bank", "")
            with open(bank_file, "r") as f:
                banks[name] = [line.strip() for line in f if line.strip()]
        return banks

    def generate_recipes(
        self,
        count: int = 24,
        seed_images: Optional[List[Path]] = None,
        base_prompt: Optional[str] = None,
    ) -> List[VariationRecipe]:
        """
        Generate N variation recipes. 
        Uses character DNA for 'character' mode.
        Uses product dimension banks for 'product' mode.
        """
        recipes = []

        # Determine the base descriptor/subject
        if self.mode == "product":
            subject_descriptor = self.product_description or "high-end professional product"
        else:
            subject_descriptor = base_prompt or self.char_descriptor or "photorealistic portrait, high detail"

        for i in range(count):
            # Deterministic but varied seeds per variation
            variation_seed = (self.anchor_seed + i * 7919 + hash(str(i))) % (2**32)
            random.seed(variation_seed)

            if self.mode == "product":
                # --- PRODUCT MODE LOGIC ---
                def pick(dim: str) -> str:
                    opts = self.banks.get(dim, [""])
                    return random.choice(opts) if opts else ""

                angle = pick("angle")
                material = pick("material")
                context = pick("context")
                lighting = pick("lighting")

                # Compose Product Prompt: [Subject], [Material], [Angle], [Context], [Lighting], [Quality]
                prompt_parts = [
                    subject_descriptor,
                    f"made of {material}",
                    angle,
                    context,
                    lighting,
                    self.quality_constants
                ]
                prompt = ", ".join(p for p in prompt_parts if p)
                
                # Metadata for filename
                filename_base = f"PROD_{i:03d}_{material.replace(' ', '_')}_{angle.replace(' ', '_')}"

            else:
                # --- CHARACTER MODE LOGIC (Existing) ---
                def pick(dim: str) -> str:
                    opts = self.banks.get(dim, [""])
                    if not opts: return ""
                    return opts[i % len(opts)] if len(opts) >= count else random.choice(opts)

                pose = pick("pose")
                view = pick("view")
                lighting = pick("lighting")
                background = pick("background")
                extras = pick("extras")
                crop = pick("crop")

                prompt_parts = [
                    crop,
                    f"{pose}, {view}",
                    subject_descriptor,
                    f"in {background}" if background else "",
                    lighting,
                    extras,
                    self.quality_constants,
                ]
                prompt = ", ".join(p for p in prompt_parts if p)
                filename_base = f"VAR_{i:03d}_{pose.replace(' ', '_')}_{lighting.replace(' ', '_')}"

            # Assign seed image round-robin if multiple provided
            seed_img = None
            if seed_images:
                seed_img = seed_images[i % len(seed_images)]

            recipes.append(
                VariationRecipe(
                    index=i,
                    seed=variation_seed,
                    pose="N/A" if self.mode == "product" else pose, # Compatibility with dataclass
                    view="N/A" if self.mode == "product" else view,
                    lighting=lighting,
                    background="N/A" if self.mode == "product" else background,
                    extras="N/A" if self.mode == "product" else extras,
                    crop="N/A" if self.mode == "product" else crop,
                    prompt=prompt,
                    filename=filename_base,
                    seed_image=seed_img,
                )
            )

        random.seed()
        return recipes


# ─── ComfyUI Dispatcher ──────────────────────────────────────────────────────

class ComfyVariationDispatcher:
    """Submits variation recipes to ComfyUI and polls for completion."""

    def __init__(self, host: str = DEFAULT_COMFY_HOST):
        self.host = host.rstrip("/")
        self.submitted: Dict[str, VariationRecipe] = {}

    def _inject_seed_image(self, workflow: Dict[str, Any], image_path: Path) -> Dict[str, Any]:
        """
        Find or add a LoadImage node for the seed image.
        Also wires FluxReduxImageEncoder if present in workflow.
        """
        wf = json.loads(json.dumps(workflow))
        prompt_block = wf.get("prompt", wf)

        # Find LoadImage node
        load_image_node = None
        for node_id, node in prompt_block.items():
            if isinstance(node, dict) and node.get("class_type") == "LoadImage":
                load_image_node = node_id
                break

        if load_image_node:
            prompt_block[load_image_node]["inputs"]["image"] = str(image_path.name)
        else:
            # Add a LoadImage node (may need manual upload via ComfyUI)
            new_id = "seed_image_loader"
            prompt_block[new_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": str(image_path.name)}
            }

        # Wire FluxReduxImageEncoder if it exists and references the seed image
        for node_id, node in prompt_block.items():
            if isinstance(node, dict) and node.get("class_type") == "FluxReduxImageEncoder":
                # Point to the LoadImage node output
                target = load_image_node or "seed_image_loader"
                prompt_block[node_id]["inputs"]["image"] = [target, 0]
                print(f"[INFO] Wired FluxReduxImageEncoder ({node_id}) to {target}")

        return wf

    def _inject_prompt(self, workflow: Dict[str, Any], prompt_text: str) -> Dict[str, Any]:
        """Inject prompt into CLIPTextEncode nodes."""
        wf = json.loads(json.dumps(workflow))
        prompt_block = wf.get("prompt", wf)
        injected = False
        for node_id, node in prompt_block.items():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                # Skip negative prompts (heuristic: text is a short list of negative terms)
                text = node.get("inputs", {}).get("text", "")
                negative_markers = ["blurry,", "low quality,", "distorted,", "worst quality,",
                                    "deformed", "bad anatomy", "extra fingers", "watermark"]
                # Only skip if it looks like a classic negative prompt (short + multiple markers)
                is_negative = len(text) < 200 and sum(1 for m in negative_markers if m in text.lower()) >= 2
                if is_negative:
                    continue
                prompt_block[node_id]["inputs"]["text"] = prompt_text
                injected = True
        if not injected:
            print("[WARN] No CLIPTextEncode node found for prompt injection!")
        return wf

    def _inject_seed_and_prefix(
        self, workflow: Dict[str, Any], seed: int, filename_prefix: str
    ) -> Dict[str, Any]:
        wf = json.loads(json.dumps(workflow))
        prompt_block = wf.get("prompt", wf)
        seed_injected = False
        for node_id, node in prompt_block.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            # Standard KSampler seed
            if ct in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced"):
                if "seed" in node.get("inputs", {}):
                    prompt_block[node_id]["inputs"]["seed"] = seed
                    seed_injected = True
            # FLUX / RandomNoise seed
            if ct in ("RandomNoise", "FluxNoise"):
                if "noise_seed" in node.get("inputs", {}):
                    prompt_block[node_id]["inputs"]["noise_seed"] = seed
                    seed_injected = True
            # SaveImage prefix
            if ct == "SaveImage":
                prompt_block[node_id]["inputs"]["filename_prefix"] = filename_prefix
        if not seed_injected:
            print("[WARN] No seed node found (looked for KSampler/SamplerCustom/RandomNoise)")
        return wf

    def build_payload(self, recipe: VariationRecipe, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Build a ComfyUI-ready workflow from a recipe."""
        wf = self._inject_prompt(workflow, recipe.prompt)
        wf = self._inject_seed_and_prefix(wf, recipe.seed, recipe.filename)
        if recipe.seed_image and recipe.seed_image.exists():
            wf = self._inject_seed_image(wf, recipe.seed_image)
        return wf

    def submit(self, recipe: VariationRecipe, workflow: Dict[str, Any]) -> Optional[str]:
        """Submit one recipe. Returns prompt_id or None."""
        try:
            import requests
            payload = self.build_payload(recipe, workflow)
            resp = requests.post(
                f"{self.host}/prompt",
                json={"prompt": payload},
                timeout=30,
            )
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")
            if prompt_id:
                self.submitted[prompt_id] = recipe
            return prompt_id
        except Exception as e:
            print(f"[ERROR] Submit failed for {recipe.filename}: {e}")
            return None

    def submit_all(self, recipes: List[VariationRecipe], workflow: Dict[str, Any]) -> List[str]:
        """Submit all recipes upfront. Returns list of prompt_ids."""
        prompt_ids = []
        for recipe in recipes:
            print(f"[SUBMIT] {recipe.filename} | seed={recipe.seed}")
            pid = self.submit(recipe, workflow)
            if pid:
                prompt_ids.append(pid)
            time.sleep(0.2)  # gentle rate limit
        return prompt_ids

    def poll_and_collect(self, prompt_ids: List[str], output_dir: Path, timeout_sec: int = 600):
        """
        Poll ComfyUI history for completion and download outputs.
        Downloads are saved to output_dir (ComfyUI also saves server-side).
        """
        try:
            import requests
        except ImportError:
            print("[ERROR] requests not installed. Install with: pip install requests")
            return {}

        completed = {}
        remaining = set(prompt_ids)
        start = time.time()

        print(f"[POLL] Waiting for {len(remaining)} jobs...")
        while remaining and (time.time() - start) < timeout_sec:
            for pid in list(remaining):
                try:
                    resp = requests.get(f"{self.host}/history/{pid}", timeout=10)
                    resp.raise_for_status()
                    hist = resp.json()
                    if pid not in hist:
                        continue
                    job = hist[pid]
                    status = job.get("status", {})
                    if status.get("completed"):
                        recipe = self.submitted.get(pid)
                        label = recipe.filename if recipe else pid
                        print(f"[DONE] {label}")
                        completed[pid] = job
                        remaining.discard(pid)
                except Exception as e:
                    print(f"[WARN] Poll error for {pid}: {e}")
            if remaining:
                time.sleep(2)

        if remaining:
            print(f"[TIMEOUT] {len(remaining)} jobs did not complete in {timeout_sec}s")
        else:
            print(f"[COMPLETE] All {len(completed)} jobs finished.")
        return completed


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Seed Image → Batch Variation Pipeline"
    )
    parser.add_argument(
        "--seed-images", "-s",
        nargs="+",
        type=Path,
        help="1-2 seed/reference image paths"
    )
    parser.add_argument(
        "--character", "-c",
        type=str,
        default=None,
        help="Character name from lore bible (e.g. 'Elara Vance')"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=24,
        help="Number of variations to generate (default: 24)"
    )
    parser.add_argument(
        "--workflow", "-w",
        type=Path,
        default=DEFAULT_WORKFLOW,
        help="Path to ComfyUI workflow JSON template"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for downloads"
    )
    parser.add_argument(
        "--comfy-host",
        type=str,
        default=DEFAULT_COMFY_HOST,
        help="ComfyUI API host"
    )
    parser.add_argument(
        "--lore-bible",
        type=Path,
        default=LORE_BIBLE,
        help="Path to world bible markdown"
    )
    parser.add_argument(
        "--base-prompt",
        type=str,
        default=None,
        help="Override character descriptor with custom base prompt"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print recipes without submitting to ComfyUI"
    )
    parser.add_argument(
        "--skip-poll",
        action="store_true",
        help="Submit and exit without polling for results"
    )

    args = parser.parse_args()

    # Resolve seed images
    seed_images = []
    if args.seed_images:
        seed_images = [p.resolve() for p in args.seed_images if p.exists()]
        if not seed_images:
            print("[ERROR] No valid seed images found.")
            sys.exit(1)
        print(f"[INFO] Using {len(seed_images)} seed image(s)")
    else:
        # Auto-discover from seed_images directory
        if SEED_IMAGES_DIR.exists():
            seed_images = sorted(SEED_IMAGES_DIR.glob("*.png")) + sorted(SEED_IMAGES_DIR.glob("*.jpg"))
            if seed_images:
                print(f"[INFO] Auto-discovered {len(seed_images)} seed image(s) from {SEED_IMAGES_DIR}")

    # Load workflow template
    workflow_path = args.workflow
    if not workflow_path.exists():
        print(f"[ERROR] Workflow not found: {workflow_path}")
        print("[HINT] Copy a FLUX2 workflow JSON from ComfyUI (Save API Format) to workflows/")
        sys.exit(1)
    with open(workflow_path, "r") as f:
        workflow = json.load(f)
    print(f"[INFO] Loaded workflow: {workflow_path}")

    # Initialize variation engine
    engine = VariationEngine(
        character_name=args.character,
        lore_bible_path=args.lore_bible,
        base_prompt=args.base_prompt,
    )
    if engine.char_descriptor:
        print(f"[INFO] Character DNA loaded for: {args.character or 'auto-detected'}")
        print(f"[INFO] Anchor seed: {engine.anchor_seed}")
    else:
        print("[INFO] Running without character DNA (no lore bible or character not found)")

    # Generate recipes
    recipes = engine.generate_recipes(
        count=args.count,
        seed_images=seed_images,
        base_prompt=args.base_prompt,
    )
    print(f"[INFO] Generated {len(recipes)} variation recipes")
    print()

    # Dry-run mode
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN — Prompts that would be submitted:")
        print("=" * 60)
        for r in recipes:
            print(f"\n--- {r.filename} ---")
            print(f"seed:  {r.seed}")
            print(f"pose:  {r.pose}")
            print(f"view:  {r.view}")
            print(f"light: {r.lighting}")
            print(f"bg:    {r.background}")
            print(f"extra: {r.extras}")
            print(f"crop:  {r.crop}")
            print(f"prompt: {r.prompt[:120]}...")
            if r.seed_image:
                print(f"seed_img: {r.seed_image}")
        print("\n" + "=" * 60)
        print(f"Total: {len(recipes)} variations")
        sys.exit(0)

    # Ensure output dir exists
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Output directory: {output_dir}")

    # Submit to ComfyUI
    dispatcher = ComfyVariationDispatcher(host=args.comfy_host)
    prompt_ids = dispatcher.submit_all(recipes, workflow)
    print(f"[INFO] Submitted {len(prompt_ids)}/{len(recipes)} jobs")

    if args.skip_poll:
        print("[INFO] Skip-poll enabled. Exiting. Check ComfyUI queue for results.")
        sys.exit(0)

    # Poll for completion
    dispatcher.poll_and_collect(prompt_ids, output_dir)
    print(f"[INFO] Outputs saved to ComfyUI's output folder and {output_dir}")


if __name__ == "__main__":
    main()
