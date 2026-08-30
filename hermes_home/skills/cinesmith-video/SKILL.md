---
name: cinesmith-video
description: Use when this Cinesmith video bot is rendering motion. Queue render_take. Never invent filenames.
version: 1.2.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, video, h3]
    category: cinesmith
---

# Cinesmith Video

Turn boarded shots into MiniMax H3 takes on Spark.

Prefer appending to `$CINESMITH_PRODUCE_DIR/queue.json`:

`{"action": "render_take", "shot_id": "SHOT_001", "mode": "i2va", "status": "pending"}`

Or POST `$CINESMITH_API/api/produce/$JOB/queue` with the same body.

Modes: `t2va` (scout, no still), `i2va` (board → take), `fl2va` (first + last), `r2va` (identity refs).

Shoot grammar: `fl2va` when the shot has `end_still`, else `i2va`. Scout is always `t2va`.

Mid-clip guides go on the shot as `guides: [{ "frame_idx": 48, "image": "boards/mid.png" }]`. The worker injects `MiniMaxH3AddGuide` only when those files exist.

Clips land in `$CINESMITH_PRODUCE_DIR/clips/`. If Spark is down, leave the queue item pending. Never invent a filename.
