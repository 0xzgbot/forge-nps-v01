---
name: cinesmith-video
description: Use when this Cinesmith video bot is rendering motion. Call render-take. Never invent filenames.
version: 1.1.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, video, h3]
    category: cinesmith
---

# Cinesmith Video

Turn boarded shots into MiniMax H3 takes on Spark.

POST `$CINESMITH_API/api/produce/$JOB/render-take` with `{ "shot_id": "SHOT_001", "mode": "i2va" }`.

Modes: `t2va` (scout, no still), `i2va` (board → take), `fl2va` (first + last), `r2va` (identity refs).

Clips land in `$CINESMITH_PRODUCE_DIR/clips/`. If Spark is down, stop. Never invent a filename.
