---
name: cinesmith-evolution-plan
description: Strategic roadmap for evolving Cinesmith into a Neural Production Studio.
---

# Cinesmith Evolution Sprint (Hackathon Strategy)

## Overview
This skill encodes the strategic development plan for evolving Cinesmith into a "Neural Production Studio" to win the Hermes & Kimi Hackathons. It prioritizes proactive intelligence and transparency over reactive automation.

## The 5 Strategic Gaps & Solutions
1. **Visibility (Reasoning Trace):** Implement `trace_log` in all agents to provide visual/textual evidence of AI thought processes for demo purposes.
2. **Reliability (Strict Schema Guard):** Use Pydantic-based validation in the `kimi_bridge` to force Kimi into compliance and trigger auto-remediation if JSON is malformed.
3. **Proactivity (Pre-Flight Validator):** Implement a proactive audit stage *before* GPU/API execution to prevent wasted compute on bad logic.
4. **Efficiency (Tiered Production):** Introduce `Rapid` vs `Hero` profiles to optimize latency and compute budget based on shot importance.
5. **Utility (Director's Override):** Enable high-priority human command interrupts that update persistent memory and trigger targeted re-runs.

## Execution Roadmap (10-Day Sprint)
- **Phase 1: Foundation (Days 1-2):** `StrictSchemaGuard` & `ReasoningTrace`.
- **Phase 2: Intelligence Depth (Days 3-4):** `Pre-Flight Validator` & Kimi-driven decision logic.
- **Phase 3: Optimization (Days 5-6):** `Tiered Production Profiles`.
- **Phase 4: Human Control (Days 7-8):** `Director's Override` interface and memory integration.
- **Phase 5: Finalization (Days 9-10):** Demo asset capture and submission preparation.

## Audit Checklist
When auditing the project, check for:
- [ ] Does every Kimi call have a corresponding reasoning trace?
- [ ] Is there a Pydantic layer preventing malformed JSON from reaching sub-agents?
- [ ] Are background shots being handled via 'Rapid' profiles to save resources?
- [ ] Can the system recover from an invalid parameter via a self-correction loop?
