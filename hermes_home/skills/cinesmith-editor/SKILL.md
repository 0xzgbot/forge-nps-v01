---
name: cinesmith-editor
description: Use when this Cinesmith editor bot is combining clips. Write edit.json then queue assemble.
version: 1.2.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags: [cinesmith, editor]
    category: cinesmith
---

# Cinesmith Editor

Write `edit.json` as an ordered list of `{shot_id, clip, muted}` naming files that exist under `$CINESMITH_PRODUCE_DIR`.

`muted: true` strips that clip's audio in the cut. Leave it false to keep H3 stereo.

Optional color pass: PUT `/api/produce/$JOB/options` `{ "color_pass": true }` before assemble.

Range retake is a video-bot job; after the new middle lands, the original heads/tails stay.

Then queue assemble (preferred):

`{"action": "assemble", "status": "pending"}` in `queue.json`

Or POST `$CINESMITH_API/api/produce/$JOB/assemble`

That runs ffmpeg and writes `cut.mp4` with H3 stereo audio kept on unmuted clips. Do not strip the soundtrack unless the row is muted.
