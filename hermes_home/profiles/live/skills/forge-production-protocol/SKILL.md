---
name: forge-production-protocol
description: High-fidelity automation workflow for transitioning Forge MediaEngine from simulation to live production hardware (DGX Spark / Dual ComfyUI hosts).
---

# Forge MediaEngine Production Protocol (FMEPP)

## Overview
This skill defines the high-fidelity automation workflow for transitioning "The Forge" from a simulation environment to live production hardware (DGX Spark / Dual ComfyUI hosts). It ensures that all generated payloads are machine-executable and that visual consistency is maintained across multi-model pipelines.

## Trigger Conditions
- Transitioning from mock/simulated testing to real API execution.
- Integrating new research findings from Kimi into the production engine.
- Running large-scale batch productions of cinematic assets.

## Core Architecture Components

### 1. The Architect (Intent $\rightarrow$ Payload)
Translates high-level concepts into model-specific JSON payloads using the following schema logic:
- **FLUX 2 Dev:** Uses structured "Cinematic Blueprints" (Subject, Environment, Lighting, Lens) to ensure adherence and minimize text artifacts.
- **Wan 2.1 / LTX 2.3:** Implements "Temporal Anchoring." The payload must include motion vectors, frame rates (FPS), and motion strength parameters derived from the anchor still's metadata.
- **ZImage Turbo:** Optimized for low-latency/low-step counts with high contrast descriptors.

### 2. The Dispatcher (Payload $\rightarrow$ Hardware)
Man-in-the-middle routing between the Architect and ComfyUI hosts:
- **Pre-flight Check:** Executes a connectivity heartbeat to `100.74.164.x:8188` and `:8189`. If hardware is unreachable, it aborts before batch start.
- **Round-Robin Routing:** Distributes payloads across available GPU instances via `aiohttp` POST requests to the `/prompt` endpoint.

### 3. The Auditor (Failure $\rightarrow$ Correction)
A closed-loop semantic remediation system using a "Taxonomy of Failure":
- **Classification:** Identifies failure type (e.g., `Temporal Drift`, `Anatomical Error`, `Semantic Overload`) based on Kimi's research findings.
- **Remediation Protocol:** Uses high-density Markdown payloads from Kimi to rewrite prompts. It applies targeted corrections (e.g., adding weight to tokens, restructuring hierarchy) rather than generic regeneration.

## Workflow Steps

1. **Ingest Research**: Parse `.rtf` or `.md` files from Downloads containing Kimi's technical deep-dives into the system logic.
2. **Update Kernels**: Update `architect_router.py` with new JSON schemas and `semantic_remediation_loop.py` with new error taxonomy logic.
3. **Connectivity Validation**: Run the dispatcher in `--check` mode to ensure all target ComfyUI ports are responsive.
4. **Live Execution**: Execute via `./forge_engine.py --live`.

## Pitfalls & Constraints
- **RTF Parsing**: Ensure `.rtf` files from macOS/Kimi are converted to plain text (e.g., using `textutil`) before ingestion to avoid parsing errors in Python.
- **Sim vs Live**: Never run a production batch without verifying the `--live` flag is active, as simulation mode will not utilize actual GPU compute.
- **Network Latency**: In high-volume batches, monitor for `aiohttp` timeouts; ensure the dispatcher implements retry logic with exponential backoff.

## Verification Steps
- [ ] Verify connectivity to all ComfyUI ports via heartbeat check.
- [ ] Run a 1-item test batch in `--live` mode and confirm presence of output file in target directory.
- [ ] Validate that `ArchitectRouter` correctly applies model-specific parameters (e.g., motion strength for Wan).