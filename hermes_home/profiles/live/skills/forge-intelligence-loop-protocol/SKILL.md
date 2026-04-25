---
name: forge-intelligence-loop-protocol
description: Protocol for the Forge NPS "Sense-Think-Act-Correct" autonomous intelligence loop.
---

# Forge NPS Intelligence Loop Protocol

This protocol defines the high-agency "Sense-Think-Act-Correct" loop used in the Forge NPS pipeline to achieve autonomous visual quality.

## Overview
The intelligence loop ensures that every shot is not just generated once, but audited and remediated using a tiered escalation strategy involving reasoning models (Hermes-3) and multimodal vision models (Kimi-VL).

## The Intelligence Loop Architecture

### 1. Sense: Multi-Modal Auditing
* **Component:** `ContinuityAuditor` / `KimiBridge`.
* **Process:** After an asset is generated, it is passed to Kimi-VL for visual inspection.
* **Output:** A structured audit report containing a consistency score, error category (e.g., character mismatch, lighting error), and a detailed mismatch description.

### 2. Think: Tiered Remediation Escalation
When an audit fails, the `RemediationLoop` initiates a three-tiered escalation process:

#### Tier 1: Skill Registry Fix (Deterministic)
* **Method:** Uses pre-defined skill templates for common error categories.
* **Use Case:** Quick fixes for predictable issues (e.g., specific quality constant injections).

#### Tier 2: Brain Diagnosis (Reasoning + Vision)
* **Component:** `NousHermesBridge` (Brain) + `KimiBridge` (Vision).
* **Process:** The failed audit report and the original prompt are sent to Hermes-3.
* **Logic:** Hermes-3 performs "reasoning over failure." It analyzes the text mismatch vs. visual error to synthesize a highly specific, revised cinematic prompt. 
* **Outcome:** A high-fidelity `revised_prompt`.

#### Tier 3: Direct Model Rewrite (Heavyweight)
* **Method:** Full direct rewrite via Kimi-VL/LLM interaction.
* **Use Case:** Complex semantic failures where the entire intent needs re-contextualization.

### 3. Act: High-Precision Generation
* **Component:** `VisualAgent`.
* **Process:** The revised prompt is passed to `VisualAgent.generate()`, which utilizes an `ArchitectRouter` to select the correct ComfyUI workflow (Flux for images, LTX 2.3 for video) and injects character consistency anchors.

## Implementation Best Practices
* **Avoid Static Prompts:** Never pass raw concept strings directly to generators; always route through a reasoning bridge (Hermes-3).
* **Memory Integration:** Every remediation outcome must be recorded in `EpisodicMemory`. This allows Hermes to "learn" from its mistakes, effectively skipping Tier 1/2 in future similar sessions via semantic recall.
* **Closed-Loop Auditing:** Always re-pass the `asset_path` of a retry into the auditor to ensure the *new* asset is what is being verified.

## Troubleshooting & Pitfalls
* **Disconnected Brain:** If `lmstudio_client` is not provided during Hermes initialization, Tier 2 will fail. Ensure the reasoning bridge is always instantiated in production.
* **Workflow Mismatch:** Ensure the `VisualAgent` can find the `.json` workflow files for both Flux and LTX kernels in the `/workflows/` directory.