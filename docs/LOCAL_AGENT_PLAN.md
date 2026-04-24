# Local Agent Implementation Plan — Forge NPS

> Each task is self-contained. An agent should read only the files listed, make only the changes described, then verify. Do not read the whole codebase. Do not refactor surrounding code.

**Project root:** `~/Desktop/forge_nps_v01`  
**Dashboard:** `http://localhost:7000`  
**LM Studio:** `http://localhost:1234` (Hermes-3 model: `Hermes-3-Llama-3.2-3B`)  
**Kimi API:** NVIDIA NIM at `https://integrate.api.nvidia.com/v1/chat/completions`  
**Spark (ComfyUI):** `http://localhost:8188`  
**Workflow file:** `~/workflows/hermes_z_image_turbo_api.json`

---

## TASK 01 — Create `core/bridge/nous_hermes_bridge.py`

**Read first:**
- `core/bridge/lmstudio_client.py` (full file, 183 lines) — understand `LMStudioClient.chat_async()` and `simple_prompt()`

**Create:** `core/bridge/nous_hermes_bridge.py`

```python
"""
NousHermesBridge — wraps LMStudioClient to give Hermes-3 a structured API.
Hermes-3 is the local creative brain: writes prompts, diagnoses failures,
generates scripts and character DNA.
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional

from core.bridge.lmstudio_client import LMStudioClient

logger = logging.getLogger("NousHermesBridge")

HERMES_SYSTEM = (
    "You are Hermes, an AI creative director specialized in visual storytelling "
    "and cinematic image generation. You think in terms of composition, lighting, "
    "character presence, and visual continuity. Be specific, vivid, and concise."
)


class NousHermesBridge:
    def __init__(self):
        self.model = os.getenv("NOUS_HERMES_MODEL", "Hermes-3-Llama-3.2-3B")
        self.client = LMStudioClient()

    @property
    def is_available(self) -> bool:
        return self.client.is_available

    # ------------------------------------------------------------------
    # Core creative methods
    # ------------------------------------------------------------------

    async def generate_shot_prompt(
        self,
        concept: str,
        director_schema: Dict[str, Any] = None,
        memory_context: str = "",
    ) -> Optional[str]:
        """Write a cinematic Stable Diffusion prompt for a shot brief."""
        user = (
            f"Shot brief: {concept}\n"
            f"{f'Memory context: {memory_context}' if memory_context else ''}\n"
            "Write a vivid, specific Stable Diffusion prompt (2-4 sentences). "
            "Include: subject, action, lighting, mood, camera angle, style."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.8,
                max_tokens=300,
            )
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[HERMES] generate_shot_prompt failed: {e}")
            return None

    async def analyze_failure(
        self,
        visual_audit_result: Dict[str, Any],
        original_prompt: str,
        memory_context: str = "",
    ) -> Optional[Dict[str, str]]:
        """Diagnose a visual audit failure and return a corrected prompt."""
        user = (
            f"A rendered image failed visual QA.\n"
            f"Original prompt: {original_prompt}\n"
            f"Audit finding: {json.dumps(visual_audit_result)}\n"
            f"{f'Memory context: {memory_context}' if memory_context else ''}\n"
            "Respond in JSON with keys: root_cause (str), fix_prompt (str — the corrected full prompt)."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.5,
                max_tokens=400,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] analyze_failure failed: {e}")
            return None

    async def generate_script(self, brief: str) -> Optional[Dict[str, Any]]:
        """
        Generate a structured shot list from a creative brief.
        Returns: {"title": str, "shots": [{"shot_id", "description", "characters", "intent"}]}
        """
        user = (
            f"Creative brief: {brief}\n\n"
            "Generate a production shot list. Return JSON with keys:\n"
            "  title (str): project title\n"
            "  shots (array): each item has shot_id (e.g. SHOT_001), description (str, "
            "  vivid visual description), characters (array of character names), "
            "  intent (one of: high_fidelity_image, fast_preview_image, video_generation)\n"
            "Generate 5-10 shots. Make descriptions cinematic and specific."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.8,
                max_tokens=1200,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] generate_script failed: {e}")
            return None

    async def generate_character(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Generate character DNA and a ComfyUI anchor prompt from a description.
        Returns structured character data.
        """
        user = (
            f"Character description: {description}\n\n"
            "Generate a complete character profile. Return JSON with keys:\n"
            "  name (str), role (str), hair (str), eyes (str), build (str),\n"
            "  clothing (str), signature (str — a signature item or detail),\n"
            "  palette (array of 3-5 hex color codes),\n"
            "  anchor_prompt (str — a detailed ComfyUI/Stable Diffusion prompt "
            "  to generate a reference portrait of this character, include all "
            "  physical details, lighting: softbox studio, neutral background)"
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=600,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] generate_character failed: {e}")
            return None

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """General chat — used by Hermes Live panel CLI."""
        # Prepend system message if not already present
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": HERMES_SYSTEM}] + messages
        try:
            resp = await self.client.chat_async(
                messages=messages,
                model=self.model,
                temperature=0.8,
                max_tokens=500,
            )
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[HERMES] chat failed: {e}")
            return f"[Hermes offline] {e}"
```

**Verify:** `python3 -c "from core.bridge.nous_hermes_bridge import NousHermesBridge; b = NousHermesBridge(); print('available:', b.is_available)"`

---

## TASK 02 — Add Kimi-VL methods to `core/bridge/kimi_bridge.py`

**Read first:**
- `core/bridge/kimi_bridge.py` (full file) — understand `_execute_request()` and the httpx pattern
- `.env` — get `NIM_ENDPOINT`, `KIMI_API_KEY`, `KIMI_VISUAL_MODEL`

**Add two methods** to the `KimiBridge` class, before the `_execute_request` method:

```python
async def audit_image(
    self,
    image_path: str,
    reference_paths: list[str],
    shot_description: str,
) -> Dict[str, Any]:
    """
    Kimi-VL visual audit: compare rendered image against character references.
    Returns: {is_consistent, confidence, issues, error_category}
    """
    import base64, pathlib

    def _b64(path: str) -> str:
        return base64.b64encode(pathlib.Path(path).read_bytes()).decode()

    content = [{"type": "text", "text": (
        f"Shot description: {shot_description}\n\n"
        "The first image is the rendered output. Subsequent images are character reference sheets.\n"
        "Check: do all characters match their references (hair color, eye color, clothing, build)?\n"
        "Respond in JSON: {\"is_consistent\": bool, \"confidence\": float 0-1, "
        "\"issues\": [str], \"error_category\": str one of PHOTOMETRIC/ANATOMICAL/SEMANTIC/NONE}"
    )}]

    try:
        img_b64 = _b64(image_path)
        ext = pathlib.Path(image_path).suffix.lstrip('.') or 'jpeg'
        content.append({"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}})
    except Exception as e:
        logger.warning(f"Could not load render image {image_path}: {e}")

    for ref_path in (reference_paths or []):
        try:
            ref_b64 = _b64(ref_path)
            ext = pathlib.Path(ref_path).suffix.lstrip('.') or 'jpeg'
            content.append({"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{ref_b64}"}})
        except Exception as e:
            logger.warning(f"Could not load reference {ref_path}: {e}")

    visual_model = os.getenv("KIMI_VISUAL_MODEL", "moonshotai/Kimi-VL-A3B-Instruct")
    payload = {
        "model": visual_model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.endpoint_url, headers=self.headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            return json.loads(raw)
    except Exception as e:
        logger.error(f"audit_image failed: {e}")
        return {"is_consistent": True, "confidence": 0.0, "issues": [], "error_category": "NONE"}


async def analyze_character_photo(self, image_path: str) -> Dict[str, Any]:
    """
    Kimi-VL reads a character photo and returns structured DNA.
    Returns: {name, hair, eyes, build, clothing, signature, palette, anchor_prompt}
    """
    import base64, pathlib

    try:
        img_b64 = base64.b64encode(pathlib.Path(image_path).read_bytes()).decode()
        ext = pathlib.Path(image_path).suffix.lstrip('.') or 'jpeg'
    except Exception as e:
        logger.error(f"analyze_character_photo: could not load {image_path}: {e}")
        return {}

    content = [
        {"type": "text", "text": (
            "Analyze this character photo and extract their visual identity. "
            "Return JSON with keys: name (infer or use 'Character'), hair (color + style), "
            "eyes (color + shape), build (body type), clothing (style + colors), "
            "signature (one distinctive detail), palette (array of 3-5 dominant hex colors), "
            "anchor_prompt (a detailed Stable Diffusion portrait prompt capturing this person exactly)"
        )},
        {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}},
    ]

    visual_model = os.getenv("KIMI_VISUAL_MODEL", "moonshotai/Kimi-VL-A3B-Instruct")
    payload = {
        "model": visual_model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.endpoint_url, headers=self.headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            return json.loads(raw)
    except Exception as e:
        logger.error(f"analyze_character_photo failed: {e}")
        return {}
```

**Verify:** File parses without error: `python3 -c "from core.bridge.kimi_bridge import KimiBridge; print('ok')"`

---

## TASK 03 — Update `agents/auditor/continuity_auditor.py` for Kimi-VL

**Read first:**
- `agents/auditor/continuity_auditor.py` (full file, 213 lines)

**Changes:**

1. Update `__init__` to accept optional `kimi_bridge`:
```python
def __init__(self, lore_bible_path: str, kimi_bridge=None):
    self.lore_bible_path = lore_bible_path
    self.lore_context = self._load_lore()
    self.kimi_bridge = kimi_bridge
```

2. Update `audit_asset` signature and add Kimi-VL branch:
```python
async def audit_asset(
    self,
    asset_description: str,
    shot_id: str,
    image_path: str = None,
    reference_paths: list = None,
) -> Dict[str, Any]:
```

3. In `audit_asset`, after initializing `report`, add before calling `_perform_semantic_audit`:
```python
        # Kimi-VL visual audit if image is available
        if image_path and self.kimi_bridge and hasattr(self.kimi_bridge, "audit_image"):
            try:
                vl_result = await self.kimi_bridge.audit_image(
                    image_path=image_path,
                    reference_paths=reference_paths or [],
                    shot_description=asset_description,
                )
                if not vl_result.get("is_consistent", True):
                    report.update({
                        "is_consistent": False,
                        "confidence_score": vl_result.get("confidence", 0.9),
                        "error_category": vl_result.get("error_category", "SEMANTIC"),
                        "mismatch_report": "; ".join(vl_result.get("issues", [])),
                        "remediation_prompt": asset_description,
                        "violations": vl_result.get("issues", []),
                        "reasoning_trace": [f"[KIMI-VL] {i}" for i in vl_result.get("issues", [])],
                    })
                else:
                    report["confidence_score"] = vl_result.get("confidence", 1.0)
                    report["reasoning_trace"] = ["[KIMI-VL] Visual audit passed."]
                logger.info(f"[KIMI-VL] Audit for {shot_id}: consistent={vl_result.get('is_consistent')}")
                return report
            except Exception as e:
                logger.warning(f"Kimi-VL audit failed, falling back to text audit: {e}")

        # Text-based fallback
        analysis_result = await self._perform_semantic_audit(asset_description)
```

**Verify:** `python3 -c "from agents.auditor.continuity_auditor import ContinuityAuditor; print('ok')"`

---

## TASK 04 — Implement `VisualAgent.generate()`

**Read first:**
- `agents/visual/visual_agent.py` (full file, 173 lines) — understand `submit_to_comfy()` and `_build_kernel_payload()`
- `core/dispatch/comfy_client.py` (full file) — understand `submit_prompt()` and `poll_job()` and `download_outputs()`

**Add this method** to the `VisualAgent` class, after `load_workflow`:

```python
    async def generate(
        self,
        shot_id: str,
        description: str,
        director_schema: Dict[str, Any] = None,
        timeout_sec: int = 300,
    ) -> Dict[str, Any]:
        """
        Full generate cycle: build payload → load workflow → submit → poll → download.
        Returns {"shot_id", "asset_path", "status", "comfy_job_id"}.
        """
        import pathlib

        await self._ensure_connectivity()

        shot_data = {
            "shot_id": shot_id,
            "description": description,
            "visual_prompt": {"subject": description, "action": ""},
            "intent": (director_schema or {}).get("intent", "high_fidelity_image"),
            "shot_index": 0,
        }

        # Load the proven Z-Image Turbo workflow
        workflow_path = pathlib.Path("~/workflows/hermes_z_image_turbo_api.json")
        if not workflow_path.exists():
            # Fallback to repo workflows/
            workflow_path = pathlib.Path(__file__).parent.parent.parent / "workflows" / "flux2_turbo.json"

        if not workflow_path.exists():
            logger.error(f"No workflow file found at {workflow_path}")
            return {"shot_id": shot_id, "status": "error", "asset_path": "", "comfy_job_id": None}

        with open(workflow_path, "r") as f:
            import json as _json
            workflow = _json.load(f)

        result = await self.submit_to_comfy(shot_data, workflow)

        if result.get("status") not in ("SUCCESS", "success"):
            logger.error(f"ComfyUI submission failed for {shot_id}: {result}")
            return {"shot_id": shot_id, "status": "error", "asset_path": "", "comfy_job_id": None}

        # Extract prompt_id from ComfyUI response
        comfy_resp = result.get("data", {})
        prompt_id = None
        if isinstance(comfy_resp, dict):
            prompt_id = comfy_resp.get("prompt_id") or comfy_resp.get("response", {}).get("prompt_id")

        if not prompt_id:
            logger.warning(f"No prompt_id returned for {shot_id}")
            return {"shot_id": shot_id, "status": "submitted", "asset_path": "", "comfy_job_id": None}

        logger.info(f"[VISUAL] {shot_id} submitted → prompt_id={prompt_id}. Polling...")

        # Poll for completion
        from core.dispatch.comfy_client import ComfyUIClient
        client = ComfyUIClient(self.comfyui_url)
        filename = await client.poll_job(prompt_id, timeout_sec=timeout_sec)

        if not filename:
            return {"shot_id": shot_id, "status": "timeout", "asset_path": "", "comfy_job_id": prompt_id}

        # Download output
        output_dir = pathlib.Path(__file__).parent.parent.parent / "data" / "outputs" / "renders"
        saved = await client.download_outputs(prompt_id, str(output_dir))
        asset_path = saved[0] if saved else str(output_dir / filename)

        logger.info(f"[VISUAL] {shot_id} complete → {asset_path}")
        return {
            "shot_id": shot_id,
            "status": "complete",
            "asset_path": str(asset_path),
            "comfy_job_id": prompt_id,
        }
```

**Verify:** `python3 -c "from agents.visual.visual_agent import VisualAgent; v = VisualAgent('http://localhost:8188'); print(hasattr(v, 'generate'))"`

---

## TASK 05 — Wire Hermes-3 into `HermesAgent.dispatch_shots()`

**Read first:**
- `core/hermes/hermes_agent.py` (full file, 261 lines) — focus on `__init__` and `dispatch_shots()` lines 70-166

**Changes:**

1. Update `__init__` to accept `hermes_bridge`:
```python
    def __init__(
        self,
        visual_agent=None,
        skill_registry=None,
        kimi_bridge=None,
        session_manager=None,
        episodic_memory: Optional[EpisodicMemory] = None,
        semantic_memory: Optional[SemanticMemory] = None,
        character_engine: Optional[CharacterConsistencyEngine] = None,
        hermes_bridge=None,   # ← add this
    ):
        ...
        self.hermes_bridge = hermes_bridge  # ← add this
```

2. In `dispatch_shots()`, replace line 129:
```python
            enriched_description = concept + memory_augmentation
```
With:
```python
            # Try Hermes-3 prompt writing first
            hermes_prompt = None
            if self.hermes_bridge and self.hermes_bridge.is_available:
                hermes_prompt = await self.hermes_bridge.generate_shot_prompt(
                    concept=concept,
                    director_schema=director_result,
                    memory_context=memory_augmentation,
                )
                if hermes_prompt:
                    await _emit("HERMES_PROMPT", {
                        "shot_id": shot_id,
                        "prompt": hermes_prompt,
                        "model": "Hermes-3",
                        "tag": "[HERMES-3 🧠]",
                    })
                    logger.info(f"[HERMES-3] Wrote prompt for {shot_id}: {hermes_prompt[:80]}...")

            enriched_description = hermes_prompt or (concept + memory_augmentation)
```

**Verify:** `python3 -c "from core.hermes.hermes_agent import HermesAgent; h = HermesAgent(); print(hasattr(h, 'hermes_bridge'))"`

---

## TASK 06 — Wire Hermes-3 into `RemediationLoop` tier 2

**Read first:**
- `core/feedback/remediation_loop.py` (full file, 214 lines) — focus on `__init__` and `_escalate_to_kimi()` lines 156-177

**Changes:**

1. Update `__init__` to accept `hermes_bridge`:
```python
    def __init__(
        self,
        hermes,
        auditor,
        session_manager,
        max_iterations: int = 3,
        hermes_bridge=None,   # ← add
    ):
        ...
        self.hermes_bridge = hermes_bridge  # ← add
```

2. In `_run_iteration`, change the tier-2 block (iteration == 2):
```python
        elif iteration == 2:
            method = "hermes_escalated"
            kimi_root_cause = await self._escalate_to_hermes(
                shot_id, mismatch, remediation_prompt, director_schema, lore_paths
            )
            fix_applied = kimi_root_cause or remediation_prompt
            logger.info(f"[REMEDIATION] iter2 hermes_escalated: {fix_applied[:80]}")
```

3. Add `_escalate_to_hermes()` method (keep `_escalate_to_kimi` for fallback):
```python
    async def _escalate_to_hermes(
        self,
        shot_id: str,
        mismatch: str,
        remediation_prompt: str,
        director_schema: Dict[str, Any],
        lore_paths: List[str],
    ) -> str:
        # Try Hermes-3 first
        if self.hermes_bridge and self.hermes_bridge.is_available:
            try:
                result = await self.hermes_bridge.analyze_failure(
                    visual_audit_result={"failure_description": mismatch},
                    original_prompt=remediation_prompt,
                )
                if result and result.get("fix_prompt"):
                    logger.info(f"[HERMES-3 🧠] Tier-2 fix: {result['fix_prompt'][:80]}")
                    return result["fix_prompt"]
            except Exception as e:
                logger.warning(f"[REMEDIATION] Hermes-3 escalation failed: {e}")
        # Fall back to Kimi
        return await self._escalate_to_kimi(shot_id, mismatch, remediation_prompt, director_schema, lore_paths)
```

**Verify:** `python3 -c "from core.feedback.remediation_loop import RemediationLoop; print('ok')"`

---

## TASK 07 — Update `ForgeOrchestrator` to wire both bridges

**Read first:**
- `core/orchestrator/forge_orchestrator.py` (full file, 187 lines)

**Changes** — in `__init__`:
```python
from core.bridge.nous_hermes_bridge import NousHermesBridge
```
Add to imports at top of file.

In `__init__`, after `self.kimi = kimi_bridge or KimiBridge(...)`:
```python
        # Hermes-3 local bridge
        try:
            self.hermes_bridge = NousHermesBridge()
            if self.hermes_bridge.is_available:
                print(f"[HERMES-3] LM Studio connected — model: {self.hermes_bridge.model}")
            else:
                print("[HERMES-3] LM Studio offline — prompt writing will use fallback")
        except Exception as e:
            print(f"[HERMES-3] Bridge init failed: {e}")
            self.hermes_bridge = None
```

In the `run()` method, when creating `HermesAgent` or when `self.hermes` is set, pass `hermes_bridge`:
```python
        # If hermes was passed in without a bridge, inject it
        if self.hermes and not getattr(self.hermes, 'hermes_bridge', None):
            self.hermes.hermes_bridge = self.hermes_bridge
```
Add this right before `[2/4] Running Kimi Narrative Intelligence...`

Also update `RemediationLoop` instantiation in `run()` if remediation is created inline — pass `hermes_bridge=self.hermes_bridge`.

**Verify:** `python3 -c "from core.orchestrator.forge_orchestrator import ForgeOrchestrator; o = ForgeOrchestrator(); print('hermes_bridge:', o.hermes_bridge)"`

---

## TASK 08 — Add `NOUS_HERMES_MODEL` to config files

**Read first:**
- `.env` (check if `NOUS_HERMES_MODEL` already exists)
- `data/config.json` (check if `nous_hermes_model` already exists)

**Edit `.env`** — add after `LMSTUDIO_CHAT_MODEL` line:
```
NOUS_HERMES_MODEL=Hermes-3-Llama-3.2-3B
```

**Edit `data/config.json`** — add key (it may already be there as `nous_hermes_model`):
```json
"NOUS_HERMES_MODEL": "Hermes-3-Llama-3.2-3B"
```

Note: `data/config.json` already has `"nous_hermes_model": "Hermes-3-Llama-3.2-3B"` (lowercase). Add uppercase version for env var consistency.

**Verify:** `python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('NOUS_HERMES_MODEL'))"`

---

## TASK 09 — Add `POST /api/hermes/chat` endpoint to dashboard

**Read first:**
- `dashboard/forge_dashboard.py` lines 490-600 — see Teach Mode endpoint pattern
- `core/bridge/nous_hermes_bridge.py` (Task 01 output)

**Add** these imports near top of `forge_dashboard.py` if not present:
```python
from core.bridge.nous_hermes_bridge import NousHermesBridge
```

**Add** a module-level bridge instance near other module-level objects (search for `spark_monitor`):
```python
_hermes_bridge = NousHermesBridge()
```

**Add** endpoint after the Teach Mode endpoint block:

```python
class HermesChatRequest(BaseModel):
    messages: list[Dict[str, str]]

@app.post("/api/hermes/chat")
async def api_hermes_chat(req: HermesChatRequest):
    """Send messages to Hermes-3 on LM Studio. Returns assistant response."""
    if not _hermes_bridge.is_available:
        raise HTTPException(status_code=503, detail="Hermes (LM Studio) is offline")
    response = await _hermes_bridge.chat(req.messages)
    await emit_hermes_event("HERMES_CHAT", {"response": response, "tag": "[HERMES-3 🧠]"})
    return {"response": response, "model": _hermes_bridge.model}
```

**Verify:** Start dashboard, then: `curl -X POST http://localhost:7000/api/hermes/chat -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"hello"}]}'`

---

## TASK 10 — Add `POST /api/hermes/generate-script` endpoint

**Read first:**
- `dashboard/forge_dashboard.py` — find where Task 09 endpoint was added, add below it
- `data/scripts/` — check if directory exists

**Add:**
```python
import re, time as _time

class GenerateScriptRequest(BaseModel):
    brief: str

@app.post("/api/hermes/generate-script")
async def api_hermes_generate_script(req: GenerateScriptRequest):
    """Generate a shot list from a creative brief using Hermes-3."""
    if not _hermes_bridge.is_available:
        raise HTTPException(status_code=503, detail="Hermes (LM Studio) is offline")
    result = await _hermes_bridge.generate_script(req.brief)
    if not result:
        raise HTTPException(status_code=500, detail="Hermes failed to generate script")

    # Save to disk
    slug = re.sub(r'[^a-z0-9]+', '_', result.get("title", "untitled").lower())[:40]
    script_dir = Path(__file__).parent.parent / "data" / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / f"{slug}_{int(_time.time())}.json"
    with open(script_path, "w") as f:
        json.dump(result, f, indent=2)

    await emit_hermes_event("SCRIPT_GENERATED", {"title": result.get("title"), "shots": len(result.get("shots", []))})
    return result
```

**Verify:** `curl -X POST http://localhost:7000/api/hermes/generate-script -H "Content-Type: application/json" -d '{"brief":"Sienna Nomad, outdoor lifestyle campaign, 5 shots"}'`

---

## TASK 11 — Add `POST /api/hermes/generate-character` endpoint

**Add** below Task 10 endpoint:

```python
class GenerateCharacterRequest(BaseModel):
    description: str

@app.post("/api/hermes/generate-character")
async def api_hermes_generate_character(req: GenerateCharacterRequest):
    """Generate character DNA from a text description using Hermes-3."""
    if not _hermes_bridge.is_available:
        raise HTTPException(status_code=503, detail="Hermes (LM Studio) is offline")
    result = await _hermes_bridge.generate_character(req.description)
    if not result:
        raise HTTPException(status_code=500, detail="Hermes failed to generate character")
    return result
```

**Verify:** `curl -X POST http://localhost:7000/api/hermes/generate-character -H "Content-Type: application/json" -d '{"description":"Sienna, 28, auburn hair, green eyes, outdoor adventurer, earth tones"}'`

---

## TASK 12 — Add `POST /api/characters/upload-anchor` endpoint

**Read first:**
- `dashboard/forge_dashboard.py` — find appropriate place to add
- `data/lore_bible/world_bible.md` — understand character block format (look for `## KEY CHARACTER:` sections)
- `data/character_banks/anchors/` — see what files exist

**Add** imports if not present: `from fastapi import UploadFile, File, Form`

**Add** endpoint:
```python
@app.post("/api/characters/upload-anchor")
async def api_characters_upload_anchor(
    name: str = Form(...),
    role: str = Form(""),
    hair: str = Form(""),
    eyes: str = Form(""),
    build: str = Form(""),
    clothing: str = Form(""),
    signature: str = Form(""),
    file: UploadFile = File(...),
):
    """Upload a character anchor image and save character DNA to world_bible.md."""
    repo_root = Path(__file__).parent.parent
    anchors_dir = repo_root / "data" / "character_banks" / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    ext = Path(file.filename).suffix or ".jpg"
    dest = anchors_dir / f"{safe_name}{ext}"

    contents = await file.read()
    dest.write_bytes(contents)

    # Append character block to world_bible.md
    bible_path = repo_root / "data" / "lore_bible" / "world_bible.md"
    character_block = f"""

## KEY CHARACTER: {name.upper()}
- **Role:** {role}
- **Physical Appearance:** {hair} hair, {eyes} eyes, {build} build
- **Clothing:** {clothing}
- **Signature Item:** {signature}
- **Anchor Image:** anchors/{safe_name}{ext}
"""
    with open(bible_path, "a", encoding="utf-8") as f:
        f.write(character_block)

    return {
        "status": "saved",
        "anchor_path": str(dest.relative_to(repo_root)),
        "name": name,
        "safe_name": safe_name,
    }
```

**Verify:** `curl -X POST http://localhost:7000/api/characters/upload-anchor -F "name=Test" -F "file=@/path/to/image.jpg"`

---

## TASK 13 — Add `POST /api/characters/analyze-photo` endpoint

**Add** below Task 12:
```python
class AnalyzePhotoRequest(BaseModel):
    image_path: str  # relative to repo root, e.g. "data/character_banks/anchors/sienna.jpg"

@app.post("/api/characters/analyze-photo")
async def api_characters_analyze_photo(req: AnalyzePhotoRequest):
    """Use Kimi-VL to extract character DNA from an uploaded anchor image."""
    from core.bridge.kimi_bridge import KimiBridge
    from core.bridge.config_manager import ConfigManager

    repo_root = Path(__file__).parent.parent
    abs_path = str(repo_root / req.image_path)

    cfg = ConfigManager()
    bridge = KimiBridge(
        endpoint_url=cfg.get("NIM_ENDPOINT"),
        api_key=cfg.get("KIMI_API_KEY"),
        config_manager=cfg,
    )
    result = await bridge.analyze_character_photo(abs_path)
    if not result:
        raise HTTPException(status_code=500, detail="Kimi-VL analysis failed")
    return result
```

**Verify:** `curl -X POST http://localhost:7000/api/characters/analyze-photo -H "Content-Type: application/json" -d '{"image_path":"data/character_banks/anchors/elara_vance.jpg"}'`

---

## TASK 14 — UI: Hermes Live CLI on Home tab

**Read first:**
- `dashboard/static/js/app.js` lines 195-328 (VIEWS.home) — find the hermes panel element (class `hermes-panel-tall`)

**Find** the hermes panel in VIEWS.home. It ends with closing `</div>` tags after the event log. **Add** a CLI footer inside the panel, just before the last closing tag of the hermes panel:

```javascript
// Hermes Live CLI input — add at the end of the hermes panel content
h('div', { class: 'hermes-cli-row', style: 'display:flex;gap:8px;padding:8px;border-top:1px solid var(--border)' },
  h('input', {
    id: 'hermes-cli-input',
    type: 'text',
    placeholder: 'Ask Hermes anything...',
    class: 'input-field',
    style: 'flex:1;font-size:12px;',
    onkeydown: `if(event.key==='Enter'){window.sendHermesChat();}`
  }),
  h('button', {
    class: 'btn-primary',
    style: 'font-size:11px;padding:6px 12px;',
    onclick: 'window.sendHermesChat()'
  }, 'Send')
),
```

**Add** this function near the top of app.js (after the `h()` helper):
```javascript
window.sendHermesChat = async function() {
  const input = $('#hermes-cli-input');
  if (!input || !input.value.trim()) return;
  const msg = input.value.trim();
  input.value = '';

  const log = $('#hermes-log');
  if (log) {
    log.innerHTML += `<div class="hermes-event" style="color:var(--cyan)">[YOU] ${msg}</div>`;
    log.scrollTop = log.scrollHeight;
  }

  try {
    const r = await fetch('/api/hermes/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ messages: [{ role: 'user', content: msg }] })
    });
    const data = await r.json();
    if (log) {
      log.innerHTML += `<div class="hermes-event" style="color:var(--text-secondary)">[HERMES-3 🧠] ${data.response}</div>`;
      log.scrollTop = log.scrollHeight;
    }
  } catch(e) {
    if (log) log.innerHTML += `<div class="hermes-event" style="color:var(--amber)">[HERMES] Offline</div>`;
  }
};
```

**Verify:** Open dashboard → Home tab → type in Hermes input → press Enter → response appears in panel.

---

## TASK 15 — UI: Script tab Hermes panel

**Read first:**
- `dashboard/static/js/app.js` — find `VIEWS.script` function (lines ~480-577). Note the exact return structure.

**Add** a Hermes generation panel at the TOP of the script tab content, before the toolbar div. Insert:

```javascript
// Hermes script generation panel
h('div', { class: 'panel', style: 'margin-bottom:16px;' },
  h('div', { class: 'panel-header' },
    h('span', { class: 'panel-title' }, '🧠 Generate Script with Hermes-3'),
    h('span', { class: 'badge-dim' }, 'LOCAL')
  ),
  h('div', { style: 'padding:12px;display:flex;flex-direction:column;gap:8px;' },
    h('textarea', {
      id: 'script-brief-input',
      placeholder: 'Describe your project... (e.g. "Sienna Nomad, 5-episode outdoor adventure, earth tones, adventure vibe")',
      class: 'input-field',
      style: 'width:100%;height:72px;resize:vertical;font-size:12px;',
    }),
    h('div', { style: 'display:flex;gap:8px;align-items:center;' },
      h('button', {
        class: 'btn-primary',
        id: 'generate-script-btn',
        onclick: 'window.generateScript()'
      }, 'Generate Script'),
      h('span', { id: 'script-gen-status', style: 'font-size:11px;color:var(--text-dim)' }, '')
    )
  )
),
```

**Add** the handler function near `sendHermesChat`:
```javascript
window.generateScript = async function() {
  const brief = $('#script-brief-input')?.value?.trim();
  if (!brief) return;
  const status = $('#script-gen-status');
  const btn = $('#generate-script-btn');
  if (status) status.textContent = 'Hermes is writing...';
  if (btn) btn.disabled = true;

  try {
    const r = await fetch('/api/hermes/generate-script', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ brief })
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    if (status) status.textContent = `✓ Generated "${data.title}" — ${data.shots?.length || 0} shots`;
    // Re-render script tab with new shots
    window._generatedShots = data.shots || [];
    ROUTER.navigate('script');
  } catch(e) {
    if (status) status.textContent = `✗ ${e.message}`;
  } finally {
    if (btn) btn.disabled = false;
  }
};
```

Update `VIEWS.script` to use `window._generatedShots` if set:
Find the line where `SHOTS` is used in the shot table and replace with:
```javascript
const shotsToShow = window._generatedShots || SHOTS;
```

**Verify:** Open dashboard → Script tab → type brief → click Generate → shot table repopulates.

---

## TASK 16 — UI: Characters tab image upload + Hermes panel

**Read first:**
- `dashboard/static/js/app.js` — find `VIEWS.characters` function (lines ~350-477). Note the character selector grid and hero section.

**Add** a Hermes + upload panel between the character selector grid and the hero section. Find the hero section div and insert before it:

```javascript
// Hermes character creation panel
h('div', { class: 'panel', style: 'margin-bottom:16px;' },
  h('div', { class: 'panel-header' },
    h('span', { class: 'panel-title' }, '🧠 Add Character'),
    h('span', { class: 'badge-dim' }, 'HERMES-3 + KIMI-VL')
  ),
  h('div', { style: 'padding:12px;display:grid;grid-template-columns:1fr 1fr;gap:16px;' },

    // Left: describe + generate
    h('div', { style: 'display:flex;flex-direction:column;gap:8px;' },
      h('div', { style: 'font-size:11px;color:var(--text-dim);margin-bottom:4px' }, 'DESCRIBE → HERMES GENERATES'),
      h('input', { id:'char-name-input', type:'text', placeholder:'Character name', class:'input-field', style:'font-size:12px;' }),
      h('textarea', {
        id: 'char-desc-input',
        placeholder: 'Describe appearance, style, role... (e.g. "Sienna, 28, auburn hair, green eyes, outdoor adventurer")',
        class: 'input-field',
        style: 'height:72px;resize:vertical;font-size:12px;'
      }),
      h('button', { class:'btn-primary', onclick:'window.generateCharacter()' }, 'Generate with Hermes'),
    ),

    // Right: upload photo
    h('div', { style: 'display:flex;flex-direction:column;gap:8px;' },
      h('div', { style: 'font-size:11px;color:var(--text-dim);margin-bottom:4px' }, 'UPLOAD PHOTO → KIMI-VL ANALYZES'),
      h('div', {
        id: 'char-upload-zone',
        style: 'border:2px dashed var(--border);border-radius:6px;padding:24px;text-align:center;cursor:pointer;transition:border-color 0.2s;',
        onclick: '$("#char-file-input").click()',
        ondragover: 'event.preventDefault();this.style.borderColor="var(--cyan)"',
        ondragleave: 'this.style.borderColor="var(--border)"',
        ondrop: 'event.preventDefault();this.style.borderColor="var(--border)";window.handleCharUpload(event.dataTransfer.files[0])'
      },
        h('img', { id:'char-upload-preview', style:'max-height:80px;display:none;margin:0 auto 8px;border-radius:4px;' }),
        h('div', { id:'char-upload-label', style:'font-size:12px;color:var(--text-dim)' }, '📷 Drop photo or click to upload'),
      ),
      h('input', { id:'char-file-input', type:'file', accept:'image/*', style:'display:none', onchange:'window.handleCharUpload(this.files[0])' }),
      h('button', { class:'btn-secondary', id:'char-analyze-btn', onclick:'window.analyzeCharPhoto()', style:'display:none' }, '👁 Analyze with Kimi-VL'),
      h('button', { class:'btn-primary', id:'char-save-btn', onclick:'window.saveCharacter()', style:'display:none' }, 'Save Character'),
    )
  ),

  // DNA preview (populated after generate or analyze)
  h('div', { id:'char-dna-preview', style:'display:none;padding:12px;border-top:1px solid var(--border);font-size:12px;color:var(--text-secondary);' })
),
```

**Add** handler functions:
```javascript
window._charUploadFile = null;
window._charDNA = null;

window.handleCharUpload = function(file) {
  if (!file) return;
  window._charUploadFile = file;
  const preview = $('#char-upload-preview');
  const label = $('#char-upload-label');
  const reader = new FileReader();
  reader.onload = e => {
    if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
    if (label) label.textContent = file.name;
  };
  reader.readAsDataURL(file);
  const analyzeBtn = $('#char-analyze-btn');
  const saveBtn = $('#char-save-btn');
  if (analyzeBtn) analyzeBtn.style.display = '';
  if (saveBtn) saveBtn.style.display = '';
};

window.analyzeCharPhoto = async function() {
  if (!window._charUploadFile) return;
  const btn = $('#char-analyze-btn');
  if (btn) btn.textContent = 'Analyzing...';

  // First upload the file
  const formData = new FormData();
  formData.append('file', window._charUploadFile);
  formData.append('name', $('#char-name-input')?.value || 'Character');
  formData.append('role', '');

  try {
    const uploadR = await fetch('/api/characters/upload-anchor', { method:'POST', body: formData });
    const uploadData = await uploadR.json();

    // Then analyze with Kimi-VL
    const analyzeR = await fetch('/api/characters/analyze-photo', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ image_path: uploadData.anchor_path })
    });
    const dna = await analyzeR.json();
    window._charDNA = dna;
    window._showCharDNA(dna);
    if (btn) btn.textContent = '✓ Analyzed';
  } catch(e) {
    if (btn) btn.textContent = '✗ Failed';
    console.error(e);
  }
};

window.generateCharacter = async function() {
  const desc = $('#char-desc-input')?.value?.trim();
  if (!desc) return;
  const preview = $('#char-dna-preview');
  if (preview) { preview.style.display = ''; preview.textContent = 'Hermes is thinking...'; }

  try {
    const r = await fetch('/api/hermes/generate-character', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ description: desc })
    });
    const dna = await r.json();
    window._charDNA = dna;
    window._showCharDNA(dna);
    $('#char-save-btn').style.display = '';
  } catch(e) {
    if (preview) preview.textContent = `✗ ${e.message}`;
  }
};

window._showCharDNA = function(dna) {
  const el = $('#char-dna-preview');
  if (!el) return;
  el.style.display = '';
  el.innerHTML = `
    <strong style="color:var(--cyan)">${dna.name || 'Character'}</strong> · ${dna.role || ''}<br>
    Hair: ${dna.hair || '—'} · Eyes: ${dna.eyes || '—'} · Build: ${dna.build || '—'}<br>
    Clothing: ${dna.clothing || '—'}<br>
    Signature: ${dna.signature || '—'}<br>
    ${(dna.palette||[]).map(c=>`<span style="display:inline-block;width:16px;height:16px;background:${c};border-radius:2px;margin:1px;"></span>`).join('')}
    ${dna.anchor_prompt ? `<br><em style="color:var(--text-dim)">${dna.anchor_prompt.slice(0,120)}...</em>` : ''}
  `;
};

window.saveCharacter = async function() {
  const dna = window._charDNA;
  const file = window._charUploadFile;
  const name = dna?.name || $('#char-name-input')?.value || 'Character';
  if (!dna && !file) return;

  const formData = new FormData();
  formData.append('name', name);
  formData.append('role', dna?.role || '');
  formData.append('hair', dna?.hair || '');
  formData.append('eyes', dna?.eyes || '');
  formData.append('build', dna?.build || '');
  formData.append('clothing', dna?.clothing || '');
  formData.append('signature', dna?.signature || '');
  if (file) {
    formData.append('file', file);
  } else {
    // Create placeholder if no file
    const blob = new Blob([''], {type:'image/jpeg'});
    formData.append('file', blob, `${name.toLowerCase().replace(/\s+/g,'_')}.jpg`);
  }

  try {
    await fetch('/api/characters/upload-anchor', { method:'POST', body: formData });
    alert(`✓ Character "${name}" saved. Reload Characters tab to see them.`);
    ROUTER.navigate('characters');
  } catch(e) {
    alert(`✗ Save failed: ${e.message}`);
  }
};
```

**Verify:** Open dashboard → Characters tab → see "Add Character" panel → drag in a photo → "Analyze with Kimi-VL" button appears.

---

## Execution Order

Run tasks in this order (some are parallel):

```
PARALLEL GROUP A (no dependencies):
  Task 01 — Create NousHermesBridge
  Task 02 — Add Kimi-VL methods to KimiBridge
  Task 08 — Add config keys

PARALLEL GROUP B (depends on Task 01):
  Task 03 — Update ContinuityAuditor
  Task 04 — Implement VisualAgent.generate()
  Task 05 — Wire HermesAgent dispatch_shots
  Task 06 — Wire RemediationLoop tier 2

SEQUENTIAL:
  Task 07 — Update ForgeOrchestrator (depends on 01, 05, 06)

PARALLEL GROUP C (depends on 01, 02):
  Task 09 — /api/hermes/chat endpoint
  Task 10 — /api/hermes/generate-script endpoint
  Task 11 — /api/hermes/generate-character endpoint
  Task 12 — /api/characters/upload-anchor endpoint
  Task 13 — /api/characters/analyze-photo endpoint

PARALLEL GROUP D (depends on Group C):
  Task 14 — UI: Hermes Live CLI
  Task 15 — UI: Script tab panel
  Task 16 — UI: Characters tab panel + upload
```

## Final Verification

After all tasks complete:
```bash
cd ~/Desktop/forge_nps_v01
python -m pytest                          # must still show 65 passed
python -m dashboard.forge_dashboard &     # start dashboard
curl -X POST http://localhost:7000/api/hermes/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Write a shot for Sienna at golden hour"}]}'
# should return a real Hermes-3 response
```
