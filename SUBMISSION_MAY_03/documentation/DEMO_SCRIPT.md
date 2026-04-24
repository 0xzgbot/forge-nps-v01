# FORGE NPS — Hackathon Demo Script & Storyboard
**Version:** 1.0 (Draft)
**Target Duration:** 75-90 Seconds
**Tone:** High-tech, Cinematic, Authoritative, "The Future of Production"

---

## I. OVERVIEW
This demo proves that FORGE NPS solves the single greatest hurdle in AI video production: **Temporal and Character Consistency.** We move from unstructured lore to a consistent, high-fidelity cinematic sequence via an automated, audited pipeline.

---

## II. STORYBOARD

| Time | Visual Scene | Audio / Narration | On-Screen Text / UI Callouts |
| :--- | :--- | :--- | :--- |
| **00:00-00:10** | **THE HOOK.** Rapid, jarring cuts of the *same* character concept looking completely different (different hair, face, clothing). High-frequency glitch transitions. | "In AI video, consistency is the wall. You create a hero... then you lose them in the next shot." | **[GLITCH EFFECT]**<br>CONSISTENCY ERROR: 0% |
| **00:10-00:25** | **THE PROBLEM.** Close up of a terminal window showing error logs or "Low Similarity" warnings. A side-by-side comparison of two failed character renders. | "Character drift destroys immersion. Manual prompting is too slow, and too unreliable for professional pipelines." | **[TERMINAL VIEW]**<br>Similarity Score: < 0.45<br>STATUS: REJECTED |
| **00:25-00:45** | **THE SOLUTION (The Pipeline).** Smooth transition to the **FORGE NPS Dashboard**. We see a Markdown file (`world_bible.md`) being 'ingested'. The terminal shows `seed_variation_pipeline.py` running. | "Introducing FORGE NPS. We transform raw lore into mathematical anchors, automating the path from concept to cinematic reality." | **[DASHBOARD VIEW]**<br>INGESTING LORE...<br>GENERATING ANCHORS... |
| **00:45-01:05** | **THE EXECUTION.** A montage of the ComfyUI queue filling up. We see the 'Audit/Remediation' loop in action on the dashboard: a shot fails $ightarrow$ error detected $ightarrow$ auto-retry $ightarrow$ pass. | "Our autonomous agents don't just render; they audit. Every shot is checked for photometric accuracy and brand alignment." | **[DASHBOARD ANIMATION]**<br>SHOT_04: [RETRYING]<br>SHOT_05: [PASS - KIMI-VL] |
| **01:05-01:25** | **THE PAYOFF.** The "Money Shot." A high-speed, cinematic montage of the 10 completed shots (Elara Vance in different environments). Smooth, slow-motion pans. Music swells to a crescendo. | "Consistent characters. Controlled aesthetics. Professional scale. This is FORGE NPS." | **[CINEMATIC MONTAGE]**<br>CONSISTENCY SCORE: 98%<br>STATUS: PRODUCTION READY |
| **01:25-01:30** | **LOGO REVEAL.** Minimalist black background. The FORGE NPS logo emerges in Cyber Cyan. | [Deep, resonant synth bass note] | **FORGE NPS**<br>Autonomy at Scale |

---

## III. PRODUCTION NOTES (Recording Instructions)

### 1. Required Screen Captures
*   **The "Drift" Montage:** Use early, failed/low-quality test renders to simulate the problem.
*   **The Pipeline:** Record `terminal` running the `--dry-run` command for Task A.
*   **The Dashboard:** High-res capture of the FastAPI dashboard (Port 7000) showing active session stats and the memory timeline.
*   **ComfyUI:** A timelapse or screen-recording of the ComfyUI queue processing the batch.

### 2. Technical Specs for Editor
*   **Aspect Ratio:** 16:9 (Cinematic).
*   **Color Grade:** Heavy emphasis on the Neo-Veridia palette (Magenta/Cyan/Obsidian).
*   **Transitions:** Use "Digital Glitch" for the problem phase and "Smooth Optical Zooms/Dissolves" for the solution phase.

### 3. Key Assets to Gather
*   `data/character_banks/anchors/*.png`
*   Final rendered MP4s from SPARK.
*   Dashboard screenshots (Status cards, Memory stats).
