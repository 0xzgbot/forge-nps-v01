# Demo Readiness Report

This report records the live validation pass for the current Forge NPS Script Studio, campaign image pipeline, Asset Vault continuity, and failure recovery work.

## Runtime Stack

- Dashboard: `http://127.0.0.1:7000`
- Director: LM Studio, model auto-detected as `qwen3.6-35b-a3b@q6_k`
- Comfy/Spark: configured private Spark endpoint, verified live
- Media root: `~/Desktop/FORGE_NPS_MEDIA`
- Reindex: startup reindexed existing media records successfully during the validation pass.

## Storyboard Provider Status

Local Spark storyboard providers were checked against the live ComfyUI model inventory.

- `flux2_dev`: available
- `flux2_klein`: available
- `z_image`: unavailable because the Z-Image model files were removed
- `z_image_turbo`: unavailable because the Z-Image Turbo model files were removed
- OpenAI image generation: not live-tested because no API key was configured
- Nano Banana / Gemini image generation: not live-tested because no API key was configured

The UI/backend now report unavailable local models before render submission instead of silently sending a broken workflow. Historical files may still live under the old `local_spark_media` folder path, but new visible output filenames use the selected model prefix such as `flux2_dev_...` or `flux2_klein_...`.

## Script Studio One-Click Run

- Script ID: `demo_one_click_asset_vault_001`
- Job ID: `scriptjob_309cdf180583`
- Title: `The Lamp That Answered`
- Director source: `lmstudio_director`
- Asset Vault package: `demo_asset_vault_sienna_desk_lamp`
- Requested flow: short brief -> script package -> coverage -> storyboard start frames -> image-to-video shots
- Status: complete
- Coverage shots: 2
- Storyboard frames: 2
- Video shots: 2 complete

Generated start frames:

- `~/Desktop/FORGE_NPS_MEDIA/local_spark_media/results/08397414-15b4-47a5-8642-902f9e844e66/flux2_dev_08397414_00001_.png`
- `~/Desktop/FORGE_NPS_MEDIA/local_spark_media/results/2bbd0a51-c319-424e-bf20-8b6ddded57b1/flux2_dev_2bbd0a51_00001_.png`

Generated video clips:

- `~/Desktop/FORGE_NPS_MEDIA/videos/script_demo_one_click_asset_vault_001/script_demo_one_click_asset_vault_001__SB_001__video_00001_.mp4`
- `~/Desktop/FORGE_NPS_MEDIA/videos/script_demo_one_click_asset_vault_001/script_demo_one_click_asset_vault_001__SB_002__video_00001_.mp4`

`ffprobe` confirmed both clips contain:

- H.264 video
- AAC audio stream
- Duration: `4.84` seconds
- Resolution: `1280x704`
- Frame rate: `25 fps`

Dialogue and audio intent were carried into video shot records:

- `SB_001` dialogue: `You just answered.`
- `SB_001` audio prompt: `Sharp electrical click, then half-second dead silence before dialogue cuts in tight.`
- `SB_002` audio prompt: `Low-frequency room tone builds, subtle metallic resonance underlies the flicker sounds; sharp inhale through nose.`

Important limitation: the audio stream exists and the prompts carry dialogue/audio direction, but audible speech was not independently transcribed or listened to during this pass.

## Asset Vault Continuity Run

- Package ID: `demo_asset_vault_sienna_desk_lamp`
- Package type: product continuity package
- Included continuity locks:
  - matte-black articulating desk lamp
  - brass dimmer knob
  - warm cone of light
  - modern maker workshop
  - teal/amber commercial grade
  - linked character reference: `Avery Coleman`

Verification:

- Script Studio storyboard prompts included `Asset Vault` package instructions.
- Prompts included product, style, prop, location, and linked character continuity text.
- Start frames were rendered through `flux2_dev` with the package text included.

## Main Campaign Pipeline Runs

### 5-Image Campaign

- Campaign ID: `demo_5_image_campaign_for_sienna_desk_lamp_premi__f9f29e`
- Result: 5 shots rendered
- Audit: 5 passes
- Observed behavior: normal Director -> Prompt Compiler -> Spark -> Audit -> Memory flow completed.

### 3-Image Batch Queue Verification

- Campaign ID: `3_image_batch_queue_verification_campaign_matte__0fc1c3`
- Result: 3 shots rendered
- Batch behavior: all 3 shots were prepared first, then submitted to ComfyUI together as a batch queue.
- Event proof: the stream emitted `Batch submitting 3 compiled image render(s) to ComfyUI...` before queueing all 3 prompts.

### 12-Image Carousel Campaign

- Campaign ID: `12_image_instagram_carousel_campaign_for_sienna__e591c2`
- Result: 12 shots rendered
- Batch behavior: all 12 compiled image renders were queued back-to-back before polling.
- Audit: 10 original passes, 2 original failures
- Retry behavior: one retry passed; one retry failed after remediation.

### 20-Image Larger Campaign

- Campaign ID: `20_image_large_campaign_for_sienna_desk_lamp_pre__7ce17a`
- Result: 20 shots rendered
- Batch behavior: all 20 compiled image renders were queued back-to-back before polling.
- Audit: 15 original passes, 5 original failures
- Retry behavior: 4 retry remediations passed, 1 remediation render timed out with a visible timeout error.
- Additional validation: the audit retry state-machine fix was exercised by successful remediations without the previous `invalid_transition:audit_started->final_pass` failure.

### TikTok / Vertical Campaign

- Campaign ID: `tiktok_vertical_5_shot_campaign_for_sienna_desk__178ade`
- Result: 5 vertical shots rendered
- Platform skill: activated TikTok-style `1080x1920`, `9:16`, hook-first, caption-safe guidance.
- Audit: 3 original passes, 2 original failures, retries attempted.

## Failure Recovery Checks

Verified failure modes:

- Bad LM Studio endpoint returns a clear connection error.
- Bad Comfy/Spark host returns a clear connection error.
- Missing Z-Image model files now return a `409` with exact missing model assets.
- Missing storyboard frames no longer force the whole Script Studio job to fail if other frames are ready; ready frames can continue into video while missing frames are marked for retry.
- Campaign cancellation wording was corrected so pending jobs after cancellation report cancellation instead of render timeout.

## UI Checks

Validated Script Studio in browser automation at desktop, laptop, and mobile widths.

- Script Studio primary flow now shows four steps: Brief, Progress, Storyboard, Videos.
- Package JSON and advanced internals are hidden from the primary flow.
- Upload controls are collapsed by default.
- `Generate Videos` is reachable on smaller screens after scroll.
- Videos step no longer routes users away to a global page as the required continuation path.
- Empty storyboard/video panels are treated as broken state and now show clearer readiness/resume messaging.

Screenshots from the UI pass:

- `/tmp/forge_script_1440x1000.png`
- `/tmp/forge_script_1024x768.png`
- `/tmp/forge_script_390x844.png`

## Automated Checks

Passed checks during this pass:

- `python3 -m pytest tests -q`
- Result: `83 passed`
- `python3 -m pytest tests/test_full_pipeline.py tests/test_script_studio_persistence.py tests/test_resilience.py -q`
- Result: `9 passed`
- `python3 scripts/smoke_forge.py --base-url http://127.0.0.1:7000`
- Result: all smoke checks passed
- `node --check dashboard/static/js/app.js`
- Result: passed
- Python compile checks for changed backend files
- Result: passed

## Known Limitations

- Prompt compilation still runs sequentially before batch submission. The ComfyUI render queue receives the compiled group together, but prompt preparation is not parallelized yet.
- Z-Image and Z-Image Turbo are unavailable until their erased model files are reinstalled.
- OpenAI and Nano Banana providers were wired/configured but not live-tested because keys were not configured.
- Script Studio video files contain audio streams and video shot records include dialogue/audio prompts, but audible dialogue quality was not independently verified by listening or transcription.
- The 20-image large campaign produced one visible remediation timeout. That is now exposed as a recoverable job issue instead of a silent failure.

## Demo-Ready Proof Points

- Main Forge campaign can run 5, 12, and 20 image jobs with grouped Comfy queue submission.
- Script Studio can take one short brief and produce saved script state, storyboard start frames, and individual video shots.
- Asset Vault continuity data is injected into storyboard prompts.
- Local storyboard model availability now reflects the real Spark/Comfy model inventory.
- The smoke suite gives a repeatable pre-push check for config, Script Studio, disabled legacy routes, media reindex, memory health, and core APIs.
