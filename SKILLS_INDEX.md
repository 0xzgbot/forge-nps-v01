# Forge NPS — Skills Library Index

> The Hermes Agent in Forge NPS ships with a curated, multi-layer skills library. This index catalogs every skill so judges, reviewers, and contributors can see what's in the box without grepping the repo.

**Total skill directories:** 127 at the top level, plus profile-mounted skill sets for `live`, `character`, `product`, and `script` profiles.

**Skills root:** [hermes_home/skills/](hermes_home/skills/)
**Profile mounts:** [hermes_home/profiles/](hermes_home/profiles/)
**Skill schema:** Each skill is a directory containing `SKILL.md` (the agent-readable instruction), and optionally `__init__.py` and supporting files.

---

## How to read this index

- **🔥 Forge Protocol** — Original Forge agent skill, defines closed-loop pipeline behavior.
- **🎬 Cinematic Original** — Forge-authored creative knowledge (style, camera, lighting, narrative).
- **🛠 ComfyUI Operating** — Forge-authored skills for orchestrating Spark / ComfyUI render execution.
- **🎯 Diagnostic** — Failure-mode knowledge consumed by audit + remediation.
- **📦 Bundled (Hermes Default)** — Stock Hermes Agent skills shipped with the framework, retained for completeness.

Skills marked with **(twin: `skill_*`)** have a duplicate `skill_`-prefixed directory containing identical content. Both are loadable; the bare-name variant is the canonical one in the index.

---

## 🔥 Forge Agent Protocols (the closed loop)

These are the skills that *make Forge agentic*. They live under [hermes_home/profiles/live/skills/](hermes_home/profiles/live/skills/) and define the Sense → Think → Act → Correct loop that turns a brief into a finished, audited campaign.

| Skill | Purpose |
|---|---|
| **forge-intelligence-loop-protocol** | High-agency Sense-Think-Act-Correct loop used in the Forge NPS pipeline to achieve autonomous visual quality. |
| **forge-nps-intelligence-loop** | The Sense-Think-Act-Correct closed-loop architecture for the Forge NPS filmmaking pipeline; moves agents from passive dispatchers to active creative directors. |
| **forge-remediation-loop-protocol** | J8/J9 closed-loop remediation — integrates automated quality auditing (J9) with autonomous remediation loops (J8) so generation errors are systematically detected *and* repaired. |
| **forge-remediation-protocol** | Operational rules for triggering, scoping, and bounding remediation retries. |
| **forge-visual-audit-protocol** | Vision-audit skill (KimiVL integration) for stamping pass/fail with scored issues. |
| **forge-production-orchestrator** | A standardized protocol for executing the complete Forge production pipeline from a single entry point — governs the transition from creative concept to ready-to-render ComfyUI payloads. |
| **forge-production-protocol** | Forge MediaEngine Production Protocol (FMEPP) — high-level production rules. |
| **forge-onboarding-pipeline** | Metadata-driven captioning workflow for training-dataset generation, ensuring image generation and automated captioning are architecturally aligned. |
| **forge-batch-training-image-gen** | Generates large batches (100+) of high-quality, diverse training images for character consistency in LoRA / Flux Redux workflows. |
| **forge-live-production-test-protocol** | FLPTP — live production self-test before each demo / campaign. |
| **forge-nps-reconstruction-protocol** | Process for rebuilding a functional AI filmmaking pipeline from "functional stubs" to an integrated agentic loop. |
| **forge-nps-agentic-integration-protocol** | How Forge NPS skills integrate with external agent frameworks. |
| **forge-nexus-architecture-protocol** | Validated 4-phase architectural pattern for the "Cognitive Operating System" that turns raw creative assets into an agentic knowledge graph. |
| **expert-image-submitter-agent** | Precise execution engine — translates generation parameters into validated, injected JSON payloads and manages their lifecycle on remote ComfyUI instances. |

**Why this matters for the hackathon:** these skills are the visible evidence that Hermes is *the pipeline brain*, not just a chat layer. Every claim in the submission about "closed learning loop" routes through these files.

---

## 🛠 ComfyUI / Spark Operating Skills

Forge-authored render-execution skills under [hermes_home/profiles/live/skills/](hermes_home/profiles/live/skills/). They are how Hermes drives Spark.

| Skill | Purpose |
|---|---|
| **comfyui-master-control** | Top-level interaction model. Splits ComfyUI work into two non-overlapping layers (discovery vs. execution). Mixing them is treated as a system failure. |
| **comfyui-mcp-image-generation-workflow** | Reference for the `comfyui-mcp` MCP process — how the Mac-side discovery server is used. |
| **comfyui-local-api-orchestration** | Direct API as the execution layer (MCP handles discovery; this handles everything else). |
| **comfyui-remote-api-orchestrator** | Executing workflows on a remote ComfyUI server (SPARK or Dual-3090) rather than locally. |
| **comfyui-remote-asset-injection-protocol** | Maps assets to prompts deterministically and loads flattened ComfyUI API JSON templates. |
| **comfyui-payload-sanitization-protocol** | Standardized procedure for preparing JSON payloads when they were generated by LLMs or enriched with metadata. |
| **comfyui-save-to-api-payload-converter** | Handles the legacy nodes-list export format; documents the newer 0.18.x subgraph-definitions format. |
| **comfyui-video-direct-injector** | Specialized execution skill for injecting prompts into standard (unwrapped) ComfyUI workflow files for video generation (Wan 2.2, LTX 2.3). |
| **comfyui-batch-burst-protocol** | Used when a single continuous background process for multi-hundred image generations is being killed by the host OS or container manager. |
| **comfyui-crash-recovery-protocol** | Process audit + script forensics playbook when an orchestration script hangs or dies. |
| **comfyui-prompt-automation-orchestrator** | Top-level prompt-automation orchestration. |
| **comfyui-api-workflow-automation** | Symlink-vs-copy workflow for integrating new or shared ComfyUI workflows into an active MCP server environment. |
| **comfyui-workflow-query-analysis** | Comprehensive guide for querying remote ComfyUI servers and analyzing workflow files locally. |

---

## 🎬 Style Specialists (cinema-literate creative library)

Twelve deep style skills, each a film-school-quality treatment of a visual movement. These are what gives Forge its visual range.

| Skill | What it encodes | Twin |
|---|---|---|
| **art_nouveau_deco_specialist** | Art Nouveau (1890–1910) and Art Deco (1920–1940). Mucha's flowing organic lines + ornate geometric elegance. | twin: `skill_art_nouveau_deco_specialist` |
| **baroque_caravaggio_specialist** | Baroque painting (1600–1750) with deep focus on Caravaggio's tenebrism and chiaroscuro. | twin: `skill_baroque_caravaggio_specialist` |
| **cyberpunk_neon_noir_specialist** | Blade Runner / Blade Runner 2049 / Akira / Ghost in the Shell. Magenta-cyan color science with hex tables, neon physics, wet-surface materials. | twin: `skill_cyberpunk_neon_noir_specialist` |
| **italian_giallo_specialist** | 1970s Italian *giallo* — Mario Bava and Dario Argento. Color-gel combinations, stylized horror/thriller atmosphere. | twin: `skill_italian_giallo_specialist` |
| **pixar_specialist** | The 12 principles of animation, character shape language, RenderMan lighting, the Pixar Story Spine, color script discipline. | twin: `skill_pixar_specialist` |
| **soviet_constructivist_brutalist_specialist** | Russian Constructivism (Rodchenko, El Lissitzky) + Brutalist architecture. Red-black-white propaganda palette, geometric abstraction. | twin: `skill_soviet_constructivist_brutalist_specialist` |
| **studio_ghibli_specialist** | Miyazaki, Takahata, and Kazuo Oga. Hand-painted backgrounds, watercolor technique, emotional vocabulary. | twin: `skill_studio_ghibli_specialist` |
| **surrealism_dali_specialist** | Dalí's paranoid-critical method, Magritte's philosophical objects, the unconscious-mind toolkit. | twin: `skill_surrealism_dali_specialist` |
| **synthwave_retrowave_specialist** | Outrun / Neon-Noir 1980s revival aesthetic, neon pink + cyan palette. | twin: `skill_synthwave_retrowave_specialist` |
| **ukiyo_e_specialist** | Edo-period (1603–1868) Japanese woodblock print: flat color, bold black outlines, Prussian blue, asymmetric composition. | twin: `skill_ukiyo_e_specialist` |
| **wes_anderson_specialist** | Symmetry, the 60-30-10 color rule, planimetric composition, Futura/Archer typography. | twin: `skill_wes_anderson_specialist` |
| **neural_aesthetic** | Forge's *system-level* style DNA framework — lighting constants, mood descriptors, structured prompt injection. | twin: `skill_neural_aesthetic` |

Companion: **neural_aesthetic_brand_bible** — Forge Architect Router Injection Standard (v1.0).

---

## 🎥 Cinematography & Camera

| Skill | Purpose |
|---|---|
| **anamorphic_lens_signature** | Anamorphic lens characteristics — oval bokeh, horizontal flares, 2.39:1 framing. |
| **drone_aerial_framing** | Aerial-perspective framing, altitude-as-emotion, top-down vs. orbit. |
| **dutch_angle_tension** | Tilted-frame psychological tension. |
| **macro_intimacy** | Macro-scale framing for emotional intimacy. |
| **pov_first_person** | First-person POV grammar. |
| **rack_focus_technique** | Pulling focus between subjects within a shot. |
| **telephoto_compression** | Long-lens spatial compression, background flattening. |
| **wide_angle_environmental** | Wide-lens environmental context, character-in-world framing. |
| **resolution_aspect_ratio** | Aspect ratio language and 1:1 / 9:16 / 16:9 / 2.39:1 selection. |

---

## 💡 Lighting

| Skill | Purpose |
|---|---|
| **dramatic_chiaroscuro** | High-contrast directional lighting, single-source modeling. |
| **fire_candlelight** | Practical warm-source lighting (candle, torch, fireplace). |
| **golden_hour_mastery** | Sunrise/sunset color science and angle-of-incidence. |
| **natural_window_light** | Soft directional indoor light, falloff control. |
| **neon_practical_lighting** | Practical neon as primary source — color temp, bloom, spill. |
| **neon_night_city** | Wide neon urban environment — composition + atmosphere. |
| **overcast_diffusion** | Soft overcast / softbox-like natural diffusion. |
| **studio_softbox_setups** | Three-point lighting, key/fill/rim configurations. |
| **underwater_aquatic_light** | Caustics, color absorption, depth-falloff. |
| **color_palette_injection** | Forced palette injection at prompt level. |

---

## 🎯 Diagnostic / Failure-Mode Knowledge

These skills encode *what goes wrong* in AI generation. They feed audit reasoning and remediation rewriting. This is where Forge's "failure as a feature" ethos lives.

| Skill | What it diagnoses |
|---|---|
| **anatomical_errors** | Incorrect joints, hand counts, distorted limbs. |
| **background_bleed** | Subject/background separation failures. |
| **character_age_drift** | Age inconsistency across shots. |
| **clothing_detail_loss** | Wardrobe degradation between renders. |
| **composition_drift** | Framing/composition inconsistency across a sequence. |
| **eye_color_mismatch** | Eye color drift. |
| **motion_blur_artifacts** | Wrong-direction or wrong-magnitude motion blur. |
| **photometric_overexposure** | Highlight clipping, blown-out exposure. |
| **scale_distortion** | Object/subject scale errors relative to environment. |
| **skin_tone_inconsistency** | Skin tone shift across shots/lighting changes. |

---

## 🧬 Continuity, Character, and Iteration

| Skill | Purpose |
|---|---|
| **character_consistency** | Four-layer anti-drift architecture: Character DNA → Character Pack → Shot Keyframes → Render Locks. (twin: `skill_character_consistency`) |
| **cinematic_consistency_protocol** | CCP v1.0 — anchoring with FLUX 2 stills and extending into LTX 2.3 / Wan 2.1 motion. |
| **cinematic_continuity** | 180° rule, eyeline matching, match cuts, shot-reverse-shot, lighting continuity, color continuity. (twin: `skill_cinematic_continuity`) |
| **ltx23_character_consistency** | Deep research on character consistency in LTX 2.3 (Lightricks 22B-parameter open-weight video model). |
| **story_spine_narrative** | Three-act structure, 11 story beats, emotional arcs, scene sequencing → visual shots. (twin: `skill_story_spine_narrative`) |
| **ensemble_group_dynamics** | Multi-character framing and group blocking. |
| **iterative_prompt_refinement** | Logic framework for semantic remediation — failures classified by domain (what broke) × severity (how badly). |

---

## 🎭 Subject Direction & Casting

| Skill | Purpose |
|---|---|
| **child_youth_direction** | Direction language for child / youth subjects. |
| **elder_authority** | Direction language for older / authority subjects. |
| **female_protagonist_framing** | Lead-female framing and presence. |
| **male_antagonist_presence** | Antagonist character framing. |
| **non_human_creature** | Creature, monster, and non-human direction. |

---

## ⏱ Format & Runtime

| Skill | Purpose |
|---|---|
| **15_second_social_content** | Vertical social-format short. |
| **30_second_tv_spot** | Broadcast TV spot construction. |
| **60_second_brand_film** | Mid-length brand-film structure. |
| **90_second_short** | Long-form short / showcase piece. |
| **product_launch_hero_shot** | Product launch hero composition. |

---

## 🏢 Industry Verticals

Vertical-specific creative briefs, ready to swap into a campaign.

`automotive` · `beauty_skincare` · `entertainment_gaming` · `explainer_educational` · `financial_professional` · `food_hospitality` · `health_wellness` · `lifestyle_aspiration` · `luxury_premium` · `sports_performance` · `streetwear_youth_culture` · `tech_innovation`

---

## 🧪 Prompt Engineering Libraries

| Skill | Purpose |
|---|---|
| **artist_reference_vocabulary** | Curated artist reference terms for prompt enrichment. |
| **negative_prompt_library** | Reusable negative prompt fragments. |
| **positive_prompt_structure** | Positive prompt scaffolding. |
| **quality_token_sets** | Quality-modifier token packs. |
| **seed_strategy** | Seed selection / locking strategy. |
| **style_suffix_library** | Suffix tokens for style coercion. |
| **ghost_machine_narrative** | Temporal narrative arc for "Ghost in the Machine" style launches. |

---

## 📐 Schemas & Workflow Reference

| Skill | Purpose |
|---|---|
| **flux2_json_schema** | FLUX 2 payload schema reference. |
| **kimi-shot-plan-schema** | Strict structured schema for Kimi's shot plan output. |
| **workflow_flux2_text_to_image** | Reference for the FLUX2 text-to-image workflow. |
| **workflow_ltx_i2v** | Reference for the LTX 2.3 image-to-video workflow. |
| **sienna-nomad-prompt-standardization** | Prompt-library standardization protocol for the Sienna Nomad AI Influencer project (EP01–EP20+). |

---

## 🔊 Sound

| Skill | Purpose |
|---|---|
| **sound_design** | Cinematic sound design language — diegetic vs. non-diegetic, foley, music cues, sonic counterparts to visual elements. (twin: `skill_sound_design`) |

---

## 🗺 Strategic / Meta

| Skill | Purpose |
|---|---|
| **forge-nps-evolution-plan** | Forge NPS Evolution Sprint (hackathon strategy doc, codified as a skill the agent can read). |
| **visual-ai-marketing-team-setup** | Team-setup playbook for visual-AI marketing. |

---

## 👥 Profile-Mounted Skill Sets

Beyond the top-level library, Hermes profiles mount their own specialist skill sets. These are the skills active when the corresponding profile is loaded.

### Profile: `character` ([hermes_home/profiles/character/skills/](hermes_home/profiles/character/skills/))
Specialty: character-DNA continuity for AI-influencer / character-driven productions.

- **visual-prompt-engineering-master-agent**
- **brand-consistency-protocol** (universal)
- **prompt-library-audit-and-rebuild**
- **sienna-nomad-gold-standard-rebuild**
- **quality-assurance-iteration-agent**
- **sienna-nomad-anchor-payload-builder**
- **kimi-vl-integration-protocol** (Kimi-VL multi-modal integration)
- **image-generation-polish-agent**
- **tiered-audit-remediation-workflow**
- **sienna-nomad-i2v-anchor-generator**
- **forge-visual-audit-protocol**

### Profile: `product` ([hermes_home/profiles/product/skills/](hermes_home/profiles/product/skills/))
Specialty: product-launch creative direction.

- **copywriting-god-agent**
- **brand-consistency-protocol**
- **marketing-strategist-agent**
- **zimage-turbo-payload-generator** (Z-Image Turbo)
- **flux-ltx-prompt-engineering-standard**

### Profile: `script` ([hermes_home/profiles/script/skills/](hermes_home/profiles/script/skills/))
Specialty: script → shot list → motion-prompt translation.

- **ltx25-beat-based-scripting** (LTX 2.5 beat-based scripting standard)
- **ltx23-prompting-workflow**
- **zimage-turbo-payload-generator**
- **sienna-nomad-gold-standard-rebuild**
- **seedance-2-prompt-standard**
- **asset-prompt-generator**
- **flux-ltx-prompt-engineering-standard**
- **grok-video-prompting-standard**

### Profile: `forgehermes` ([hermes_home/profiles/forgehermes/skills/](hermes_home/profiles/forgehermes/skills/))
The default Forge-Hermes operator profile — mounts the bundled Hermes default set (see "Bundled" below) for general-purpose work.

### Other profiles
[director_planner](hermes_home/profiles/director_planner/), [compiler](hermes_home/profiles/compiler/), [audit_judge](hermes_home/profiles/audit_judge/), [coverage_critic](hermes_home/profiles/coverage_critic/), [continuity_guard](hermes_home/profiles/continuity_guard/), [remediator](hermes_home/profiles/remediator/) — each defined by `SOUL.md` + `config.yaml`. These are role-specialized profiles invoked at specific pipeline stages.

---

## 📦 Bundled (Hermes Default)

These are the stock skills shipped with the Hermes Agent framework (see [`.bundled_manifest`](hermes_home/skills/.bundled_manifest)). Forge retains them for completeness and general-purpose tasks; they are not Forge-original creative skills.

`apple` · `autonomous-ai-agents` · `creative` · `data-science` · `devops` · `diagramming` · `dogfood` · `domain` · `email` · `feeds` · `gaming` · `gifs` · `github` · `inference-sh` · `mcp` · `media` · `mlops` · `note-taking` · `productivity` · `red-teaming` · `research` · `smart-home` · `social-media` · `software-development` · `yuanbao`

The `.bundled_manifest` lists 76 underlying upstream skills (apple-notes, github-pr-workflow, p5js, polymarket, claude-code, codex, dspy, llama-cpp, manim-video, opencode, etc.) bundled across these directory groups.

---

## Skill counts at a glance

| Category | Count |
|---|---|
| Forge Agent Protocols (live profile) | **14** |
| ComfyUI / Spark Operating Skills | **13** |
| Style Specialists (Forge-original cinema) | **12** (× duplicate twins) |
| Cinematography & Camera | **9** |
| Lighting | **10** |
| Diagnostic / Failure-Mode | **10** |
| Continuity, Character, Iteration | **7** |
| Subject Direction / Casting | **5** |
| Format & Runtime | **5** |
| Industry Verticals | **12** |
| Prompt-Engineering Libraries | **7** |
| Schemas & Workflow Reference | **5** |
| Sound | **1** |
| Strategic / Meta | **2** |
| Profile-Mounted (character + product + script) | **24** unique |
| Bundled Hermes Default | **25** directories (76 upstream) |
| **Top-level skill directories** | **127** |

---

## Status notes

- `skill_*`-prefixed twins of 16 style/continuity skills exist as exact byte-identical copies of their bare-named counterparts. They are kept in place for runtime stability; canonical name is the bare form.
- The Forge agent protocols (the closed loop) live primarily under [hermes_home/profiles/live/skills/](hermes_home/profiles/live/skills/), not under the top-level [hermes_home/skills/](hermes_home/skills/) library. This is by design — they are *operator* skills, not *creative* skills.
- Skills that emit machine-readable schemas (`flux2_json_schema`, `kimi-shot-plan-schema`) include an `__init__.py` so they can be referenced from Python orchestration code.
- All skill directories are validated at runtime by the Hermes profile loader; missing `SKILL.md` files are skipped without crashing.
