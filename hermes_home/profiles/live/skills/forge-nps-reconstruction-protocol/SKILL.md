---
name: forge-nps-reconstruction-protocol
description: A protocol for rebuilding a broken or stubbed AI filmmaking pipeline into a functional agentic loop.
---

# Forge NPS Rapid Reconstruction Protocol

This skill outlines the process for rebuilding a functional AI filmmaking pipeline (Forge NPS) from a state of "functional stubs" to an integrated agentic loop.

## Trigger
Use when an existing project consists primarily of UI shells, mock data, or disconnected service stubs, and needs to be converted into an autonomous agentic system for a deadline/hackathon.

## Workflow

### 1. Audit & Reality Check
* Do not trust the documentation/plan. Run a filesystem audit (e.g., `os.path.exists`) to verify which files are real logic versus empty stubs.
* Categorize existing files into: **Functional**, **Stubs (Logic present but mock data used)**, and **Missing**.

### 2. Establish the "Nervous System" (Bridges)
Before building agents, build the communication layer:
* **Creative Bridge:** Implement a bridge for the primary LLM (e.g., `NousHermesBridge` for LM Studio) to handle prompting and failure analysis.
* **Visual Bridge:** Implement a multimodal bridge (e.g., `KimiBridge`) that can accept local image paths and return structured JSON audits.

### 3. Build the "Muscles" (Execution Agents)
Implement agents that perform heavy lifting:
* **Visual Agent:** Must handle ComfyUI API communication, payload construction (using existing workflow JSONs), and polling for completion/asset retrieval.

### 4. Implement the "Brain" (Orchestration & Intelligence)
Transform passive dispatchers into active directors:
* **Hermes Agent:** Instead of just passing strings, the agent must call the Creative Bridge to *generate* content and use the failure analysis logic to *remediate* errors.
* **The Loop:** Connect the Auditor $\rightarrow$ Hermes $\rightarrow$ Visual Agent in a closed-loop remediation cycle.

### 5. Build the "Cockpit" (Dashboard)
Create a UI that reflects the internal agent state:
* **Event Streaming:** Use a polling or WebSocket mechanism to stream agent logs (`[AGENT] MESSAGE`) to a terminal window in the dashboard. This provides the visual "proof of thought" required for demos.
* **Command Center:** Wire buttons (Run Campaign, Add Character) to real API endpoints rather than UI-only triggers.

## Pitfalls & Lessons Learned
* **The "Stub Trap":** Many projects appear functional because the UI works, but they lack the backend logic. Always verify file contents via `read_file`.
* **Indentation/Parsing Errors:** When performing massive rewrites via automation, use robust string replacement or complete file overwrites rather than fuzzy regex to avoid breaking Python indentation.
* **Demo Narrative:** For hackathons, prioritize the "Intelligence Loop" (Prompt $\rightarrow$ Render $\rightarrow$ Audit $\rightarrow$ Fix) over peripheral features like product catalogs or script parsers.
