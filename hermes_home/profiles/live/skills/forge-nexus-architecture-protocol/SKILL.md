---
name: forge-nexus-architecture-protocol
description: Validated 4-phase architecture for building a "Cognitive Operating System" that transforms creative assets into an agentic knowledge graph.
---

# Forge Nexus: Multi-Phase Intelligence Architecture

This skill outlines the validated 4-phase architectural pattern for building a "Cognitive Operating System" that transforms raw creative assets into an agentic knowledge graph.

## Overview
The architecture follows a dependency chain designed for hackathon speed and incremental testability: **Parse $\rightarrow$ Persist $\rightarrow$ Graph $\rightarrow$ Interface**.

## Phase 1: Manifest Layer (Parsing)
**Goal:** Transform unstructured files into structured, hash-verified JSON manifests.
- **Core Logic:** Implement specialized parsers (ComfyUI, Prompt/Markdown, Character/YAML).
- **Output Structure:** A `.forge-nexus/manifests/` directory containing individual JSON files for every asset and a `project.json` registry.
- **Key Benefit:** Allows Phase 2 to work without re-parsing raw files; provides immediate structured context.

## Phase 2: Persistence Layer (Storage & Search)
**Goal:** Provide high-speed relational querying and semantic retrieval.
- **Database:** SQLite (`forge.db`) storing full JSON blobs in `raw_manifest` columns alongside indexed metadata (IDs, names, counts).
- **Search Engine:** Lightweight BM25 implementation for keyword-based "semantic" search without the overhead of a vector database.
- **Key Benefit:** Enables rapid lookup and prevents redundant file I/O.

## Phase 3: Graph Engine (Reasoning)
**Goal:** Enable dependency analysis and impact tracing.
- **Implementation:** Use `NetworkX` to build a `MultiDiGraph` from the SQLite relationships.
- **Capabilities:**
    - `get_dependencies`: Forward traversal (What does X use?).
    - `get_impact`: Reverse traversal (If I change X, what breaks?).
    - `find_path`: Pathfinding between disparate assets.
- **Key Benefit:** Provides the "intelligence" required for agentic decision-making.

## Phase 4: MCP Server (Interface)
**Goal:** Expose all capabilities to LLMs via Model Context Protocol.
- **Tool Definitions:**
    - `forge_query`: Wrapper for BM25 search.
    - `forge_context`: Retrieval of full asset manifests.
    - `forge_impact`: Interface for impact analysis.
    - `forge_trace`: Interface for relationship pathfinding.
- **Key Benefit:** Turns the intelligence engine into a set of actionable tools for an agent (e.g., Hermes).

## Implementation Pitfalls & Lessons Learned
- **Schema Mismatches:** Ensure SQLite columns align exactly with parser outputs; use `raw_manifest` JSON blobs to handle evolving schemas without constant migrations.
- **Circular Dependencies:** When building the graph, ensure the implementation handles potential cycles in character $\leftrightarrow$ prompt relationships gracefully.
- **Testing Strategy:** Test each phase in isolation using dummy data before integrating the full pipeline.
