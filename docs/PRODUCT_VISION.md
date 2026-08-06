# Cinesmith — Product Vision (Hermes-first)

## North star

Cinesmith is a **Hermes-led virtual production agency**, not a script runner.

The user talks to an agency brain. Hermes **plans, routes skills, compiles prompts, dispatches Spark, audits, remediates, and writes memory** in real time. Fixed pipelines exist only as **internal tools** Hermes (or advanced users) can invoke—not as the primary mental model.

## Product surfaces (user language)

| UI name | What Hermes does | Not called |
| --- | --- | --- |
| **Create** | Agency home: start work, see readiness, memory tips | “pipeline picker” |
| **Images** | Live campaign: brief → Director plan → compile → Spark → audit | batch script |
| **Stories** | Multi-beat narrative production (brief → frames → clips) | Script Studio |
| **Videos** | Motion from selected stills / story frames | render recipe only |
| **Characters / Assets** | Continuity locks Hermes reuses across runs | static libraries only |
| **Memory** | Agency learning: what worked, failed, retried | log dump |

## Engineering reality (internal)

- HTTP paths may still say `/api/script/*` for compatibility.
- `data/scripts/` stores **story project** JSON (legacy folder name).
- Repo `scripts/` = **dev/ops utilities**, never user-facing product.

## Design rules

1. Prefer **agent status language** (“Hermes is planning…”, “Spark is rendering…”) over “step 3 of pipeline.”
2. Default UI is **creator / agency**; Advanced Mode reveals pipeline knobs.
3. Never imply the product is “paste a screenplay and run a fixed script.”
4. Isolation: Hermes always uses repo-local `hermes_home/`, never hijack `~/.hermes`.

## Adobe-tier bar (working checklist)

| Surface | Bar |
| --- | --- |
| Agency home | EP console: brief, Hermes chat, production timeline, command palette |
| Power user | ⌘K everywhere, keyboard workspace jumps, guided tooltips |
| Production | Live stage track (plan → compile → render → audit → memory) |
| Handoff | Story package ZIP + continuity score + audio honesty |
| Trust | Stack readiness chips, isolation guarantee, structured errors |

## Keyboard

| Shortcut | Action |
| --- | --- |
| ⌘/Ctrl+K | Command palette |
| ⌘/Ctrl+Enter | Run with Hermes (Images) / Produce story (Stories) |
| 1–8 | Agency → … → Memory |
| ? | Help |
