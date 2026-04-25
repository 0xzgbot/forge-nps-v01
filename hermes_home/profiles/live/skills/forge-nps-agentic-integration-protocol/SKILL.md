---
name: forge-nps-agentic-integration-protocol
description: Architectural standard for integrating Nous Hermes into Forge NPS as a Cognitive OS.
---

# Skill: Forge NPS Agentic Integration Protocol

## Overview
This skill defines the architectural standard for integrating the Nous Research Hermes Agent into the Forge NPS "Cognitive Operating System." It prevents the common pitfall of treating integration scripts as the agent itself and instead treats them as specialized tools/actuators.

## Core Philosophy
- **The Engine (Nous Hermes):** The autonomous reasoning loop, tool registry, and memory system (FTS5 SQLite). This is the "Brain."
- **The Actuators (Forge Bridges):** Stateless Python drivers in `core/bridge/` that interface with ComfyUI, Kimi-VL, etc. These are the "Hands."
- **The Context (Project Nexus):** A Knowledge Graph (NetworkX/Semantic Search) providing structural project truth. This is the "Map."

## Implementation Workflow

### 1. The Engine Deployment (Daemonization)
Instead of running agent logic inside the dashboard, deploy a standalone `hermes_engine/` service.
- Create a `forge_daemon.py` within the cloned Nous repository.
- Initialize the `AIAgent` class from `run_agent.py`.
- Expose a FastAPI gateway on a dedicated port (e.g., 8001) to handle dashboard requests via `/api/hermes/chat`.

### 2. Tool Registration (The Skill Injection)
Never write agentic logic in `core/`. Instead, register Forge capabilities as formal Nous Tools.
- **Step A:** Ensure bridges in `core/bridge/` are stateless and idempotent.
- **Step B:** Create a registration script in `hermes_engine/tools/forge/`.
- **Step C:** Use the Nous `tools/registry.py` to define JSON schemas for these tools (e.g., `comfyui_generate`, `kimi_audit`).
- **Step D:** The agent now "discovers" these capabilities through its own reasoning loop.

### 3. Nexus Integration (Semantic Awareness)
Connect the Agent's memory to the Knowledge Graph via the Model Context Protocol (MCP).
- Implement a `query_nexus` tool within the Nous registry.
- This tool allows the agent to perform semantic lookups against the Project Nexus graph, enabling "situational awareness."
- Implement an `update_nexus` tool to allow the agent to autonomously update the graph based on task completion (closing the loop).

## Pitfalls & Anti-Patterns
- **DO NOT** write `if/else` logic in `core/` to mimic an agent. This creates "hollow" intelligence and technical debt.
- **DO NOT** treat local integration scripts as the "source of truth" for the agent's reasoning.
- **DO NOT** confuse the Agent's episodic memory (SQLite) with the Project's structural memory (Knowledge Graph). They are complementary, not redundant.

## Verification Steps
1. Verify `AIAgent` can be instantiated in a headless environment.
2. Verify that calling a registered Forge tool via the `AIAgent` loop produces the expected side effect in ComfyUI/Kimi-VL.
3. Verify that agent decisions are driven by the Tool Schema, not hardcoded paths.
