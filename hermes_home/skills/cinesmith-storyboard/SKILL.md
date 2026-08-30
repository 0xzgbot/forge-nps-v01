---
name: cinesmith-storyboard
description: Use when this Cinesmith storyboard bot is breaking a script into shots and boards.
version: 1.2.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, storyboard]
    category: cinesmith
---

# Cinesmith Storyboard

Write `shots.json` as `{ "shots": [{ "id", "purpose", "visual", "duration_sec", "camera", "audio", "h3_mode", "end_still", "guides", "status" }] }` and `storyboard.md` tied to those ids.

Then queue boards on the 3090s (preferred) by appending `queue.json` items:

`{"action": "render_board", "shot_id": "SHOT_001", "status": "pending"}`

The worker splits those across 3090 A and 3090 B. If both boxes are down, items stay `waiting_for_host`.

Scout mode skips boards.

Fewer strong shots beat a long empty list. H3 is the camera, not the pencil — stills come from Flux on the 3090s. Drop a mid-clip guide on a shot as `guides: [{ "frame_idx": 48, "image": "boards/mid.png" }]` only when that file exists.
