# Forge NPS — Hackathon Media Production Checklist

This is every piece of media you need to generate, screenshot, or record to support your Discord post and X thread. Check them off as you go.

---

## 🎬 PRIORITY 1: The Video Demo (Required)

**This is the single most important asset.** The NousResearch hackathon explicitly asks for a video demo. Judges will watch this first.

### Specs
- **Duration:** 60–90 seconds (can extend to 3 min if pacing is tight)
- **Resolution:** 1920×1080 minimum
- **Format:** MP4 (H.264)
- **Audio:** Voiceover or text captions. Background music optional.
- **Where to host:** YouTube, Vimeo, or X native video

### Recommended 90-Second Script

| Time | Visual | Audio / Text |
|------|--------|--------------|
| 0:00–0:05 | Best rendered image full screen | "Forge NPS" title card |
| 0:05–0:15 | Dashboard → enter brief → click Run Campaign | "Enter a brief. Run a campaign." |
| 0:15–0:30 | Event stream scrolling: `kimi_raw` → `kimi_plan` → `kimi_review` → `compiler` → `spark` | "Five models. One pipeline. Every stage visible." |
| 0:30–0:45 | Open shot lightbox → scroll through provenance fields | "Every shot has a paper trail." |
| 0:45–1:00 | Click a failed shot → Re-Audit → Remediate → retry lineage appears | "Failures aren't hidden. They're branched." |
| 1:00–1:15 | Memory health endpoint JSON + TouchDesigner promo clip | "Memory is telemetry. And the pipeline promotes itself." |
| 1:15–1:30 | Fast montage of renders → tagline | "Forge NPS. Every shot, accounted for." |

### Recording Tips
- Use OBS or QuickTime Player to screen-record the dashboard
- Record at 1920×1080, 30fps
- If audio is noisy, use text captions instead of voiceover
- Export as MP4, upload to YouTube as unlisted or public

---

## 📸 PRIORITY 2: Screenshots (Required for X Thread)

### Screenshot A: Shot Provenance Detail
**Where:** Open any rendered shot in the dashboard lightbox/detail view.
**What to capture:**
- Kimi plan fields (visual brief, rationale, constraints)
- Hermes compiled prompt + negative prompt
- Skills used list
- Spark output (prompt ID, seed)
- Audit status/score

**Why:** Tweet 6 references this. Discord post section 1 references this.

### Screenshot B: Retry Lineage
**Where:** Find a shot that has `retry_of` populated, or run remediation on a failed shot.
**What to capture:**
- Original shot ID
- Remediated shot with `retry_of` pointing to original
- Final audit outcome on the retry
- The lineage chain visible in the UI

**Why:** Tweet 7 explicitly says "[screenshot of retry lineage]". This is your biggest differentiator.

### Screenshot C: Memory Health Endpoint
**Where:** `GET /api/memory/health` in browser or curl.
**What to capture:**
- The JSON response showing `total_events`, `unknown_event_types`, `orphan_remediation_events`, `shots_missing_audit_after_render`
- Preferably with some non-zero counts so it looks real

**Why:** Tweet 8 references this. Shows observability.

### Screenshot D: Live Event Stream
**Where:** Dashboard during an active campaign run.
**What to capture:**
- The NDJSON/event stream panel showing `kimi_raw`, `kimi_plan`, `compiler`, `spark`, `memory`
- Preferably mid-stream so multiple event types are visible

**Why:** Shows the pipeline is alive and observable.

### Screenshot E: Settings / Connection Tests
**Where:** Dashboard Settings page.
**What to capture:**
- Kimi endpoint configured + "Test Connection" success
- LM Studio host/model configured
- ComfyUI host configured

**Why:** Judges want to see it's not hardcoded/fake.

---

## 🎨 PRIORITY 3: Creative Output Images (Required for Tweet 9)

### Image Collage
**What:** A 2×2 or 3×3 grid of your best ComfyUI renders.
**Contents:**
- 1 hero wide shot (golden hour, cinematic)
- 1 character portrait (cyberpunk director or similar)
- 1 abstract/volumetric shot
- 1 "audit gate" typography shot (PASS/FAIL)
- 1 memory crystal shot
- 1 forge interior/server cathedral shot

**How to make:**
```bash
# Use ImageMagick or any collage tool
# Or just use Canva / Figma
```

**Format:** 1200×1200 or 1920×1080, PNG or JPG
**Why:** Tweet 9 says "[image collage]". This proves the pipeline actually produces things.

### Individual Hero Images
Generate or select your best 4–6 renders and export them as individual high-res images. These work as:
- X thread image attachments
- Discord embeds
- Thumbnails

---

## 🎞️ PRIORITY 4: TouchDesigner Promo Clips (Optional but Strong)

If you build the TD 2025 showcase kit, record short clips of:

| Clip | Duration | Use |
|------|----------|-----|
| Genesis particle birth | 3–5s | Tweet 9 attachment, video B-roll |
| Five Minds orbital streams | 3–5s | Tweet 9 attachment, video B-roll |
| Audit Gate portal | 3–5s | Tweet 7 visual, video B-roll |
| Memory Palace crystals | 3–5s | Tweet 9 attachment |
| Final output convergence | 5–10s | Video closing |

**How:** Open each `.toe`, press F1, record with OBS or QuickTime.

---

## 🖼️ PRIORITY 5: Social Card / Thumbnail (Required)

### X Card (1200×675)
- Title: "Forge NPS"
- Subtitle: "Every shot, accounted for"
- One hero render as background
- Dark gradient overlay for text readability

### YouTube Thumbnail (1280×720)
- Same as X card but more clickbaity
- Add "5 AI Models → 1 Pipeline" as hook text
- Use bold sans-serif font, high contrast

### Discord Embed Image (optional)
- 1200×630
- Clean, readable at small sizes

---

## 📋 FULL CHECKLIST

### Video
- [ ] 60–90 second demo video recorded and exported as MP4
- [ ] Video uploaded to YouTube/Vimeo/X
- [ ] Video link copied into Discord post and Tweet 1

### Screenshots
- [ ] Screenshot A: Shot provenance detail (Kimi plan + Hermes prompt + audit)
- [ ] Screenshot B: Retry lineage (`retry_of` chain visible)
- [ ] Screenshot C: Memory health endpoint JSON
- [ ] Screenshot D: Live event stream during campaign
- [ ] Screenshot E: Settings page with connection tests passing

### Creative Images
- [ ] Image collage (2×2 or 3×3 grid of best renders)
- [ ] Hero image 1 (cinematic wide shot)
- [ ] Hero image 2 (character portrait)
- [ ] Hero image 3 (abstract/volumetric)
- [ ] Hero image 4 (audit typography)
- [ ] Hero image 5 (memory crystal)
- [ ] Hero image 6 (forge interior)

### TouchDesigner Clips (Optional)
- [ ] Genesis particle birth clip
- [ ] Five Minds orbital clip
- [ ] Audit Gate portal clip
- [ ] Memory Palace clip
- [ ] Output convergence clip

### Social Assets
- [ ] X Card (1200×675)
- [ ] YouTube Thumbnail (1280×720)
- [ ] Profile/banner update (optional)

---

## 🚀 QUICK-START: Generate the Creative Images

If you haven't generated the media yet, run these campaigns through Forge NPS:

```bash
cd /Users/zgbot/Desktop/forge_nps_v01
# Launch dashboard
python3 -m dashboard.forge_dashboard
```

Then run campaigns for these briefs (or use the prompts in `comfy_prompts/shot_prompts.json`):

1. **Hero Wide:** "Trail runner crests granite ridge, golden hour, anamorphic lens flare, cinematic wide shot, photorealistic"
2. **Director Portrait:** "Cyberpunk film director, neon cyan rim lighting, holographic UI reflected in visor, 85mm lens"
3. **Engineer Portrait:** "Prompt engineer, purple violet lighting, holographic code streams, augmented reality glasses"
4. **Renderer Portrait:** "GPU artist, orange amber lighting, exposed circuit patterns, glowing GPU core, server room"
5. **Auditor Portrait:** "Quality auditor, green scanning beam, camera lens eye, dark control room"
6. **Forge Interior:** "Futuristic render farm interior, thousands of GPUs, fiber optic cables, cyan purple ambient light, volumetric fog"
7. **PASS Typography:** "Glowing green PASS typography, holographic stamp, particle burst, futuristic UI, transparent background"
8. **FAIL Typography:** "Glowing red FAIL typography, glitch distortion, digital corruption, futuristic UI, transparent background"
9. **Memory Crystal:** "Beautiful campaign photo frozen inside crystal octahedron, warm tungsten lighting, museum display"

Save all outputs to `/Users/zgbot/Desktop/FORGE_NPS_MEDIA/images/`

---

## 📝 FINAL ASSEMBLY

Once all media is ready, update these files:

1. **Discord post:** Fill in `[link]` for Video and X Thread
2. **X thread:** Fill in `[link]` for Repo, Demo, Gallery
3. **Upload screenshots** to an image host (Imgur, GitHub assets, or X native)
4. **Post X thread** with image attachments on the correct tweets
5. **Paste Discord post** into the NousResearch Discord submissions channel

---

*Check everything off = submission ready.*
