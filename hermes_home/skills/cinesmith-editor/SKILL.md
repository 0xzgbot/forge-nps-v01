---
name: cinesmith-editor
description: Use when this Cinesmith editor bot is combining clips. Write edit.json then assemble the cut.
version: 1.1.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, editor]
    category: cinesmith
---

# Cinesmith Editor

Write `edit.json` as an ordered list of `{shot_id, clip}` naming files that exist under `$CINESMITH_PRODUCE_DIR`.

Then assemble:

POST `$CINESMITH_API/api/produce/$JOB/assemble`

That runs ffmpeg and writes `cut.mp4` with H3 stereo audio kept. Do not strip the soundtrack.
