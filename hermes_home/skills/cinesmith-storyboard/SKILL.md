---
name: cinesmith-storyboard
description: Use when this Cinesmith storyboard bot is breaking a script into shots and boards.
version: 1.1.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, storyboard]
    category: cinesmith
---

# Cinesmith Storyboard

Write `shots.json` as `{ "shots": [{ "id", "purpose", "visual", "duration_sec", "camera", "audio", "h3_mode", "status" }] }` and `storyboard.md` tied to those ids.

Then paint boards on the 3090s:

POST `$CINESMITH_API/api/produce/$JOB/render-board` with `{ "shot_id": "SHOT_001" }`

Fewer strong shots beat a long empty list. H3 is the camera, not the pencil — stills come from Flux on the 3090s.
