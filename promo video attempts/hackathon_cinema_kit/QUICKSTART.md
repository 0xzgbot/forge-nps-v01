# Forge Cinema Kit — Quick Start

## What You Just Got
A completely different video direction from the first kit. This one is **cinematic, dark, and abstract** — showing the Forge app as an infinite AI studio that scales from a single prompt to a global media empire.

---

## 5-Minute Setup

### 1. Generate Source Images (use Forge/ComfyUI)
```bash
cd /Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit

# Scene 1 hero images
cat comfy_prompts/spark_images.json | jq '.images[] | .prompt'

# Scene 4 social frames
cat comfy_prompts/social_mockups.json | jq '.images[] | .prompt'

# Scene 5 trailer shots
cat comfy_prompts/theater_trailer.json | jq '.images[] | .prompt'
```
Save outputs to `assets/` with the IDs from the JSON files.

### 2. Build the TouchDesigner Network
1. Open **TouchDesigner**
2. Open the **Textport** (Alt+T)
3. Paste:
```python
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/build_master_network.py").read())
```
4. Then paste each scene script:
```python
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_spark.py").read())
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_mitosis.py").read())
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_forge.py").read())
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_social.py").read())
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_theater.py").read())
exec(open("/Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit/td_scripts/scene_infinite.py").read())
```

### 3. Replace Placeholders
- In `/project1/scene_spark/source_image` → point to your generated hero image
- In `/project1/scene_mitosis/source_image` → same or different hero
- In `/project1/scene_social` → load social frames into instances
- In `/project1/scene_theater/trailer_content` → point to your trailer frames

### 4. Render
- Set `/project1/movie_out` file path
- Hit the **+** button on movie_out to start recording
- Or use **Export Movie** dialog for higher quality

### 5. Assemble
```bash
cd /Users/zgbot/Desktop/forge_nps_v01/hackathon_cinema_kit
./ffmpeg_scripts/assemble_with_music.sh
```

---

## Scene Cheat Sheet

| Scene | Duration | Vibe | Key TD Technique |
|-------|----------|------|------------------|
| 1. Spark | 8s | Mysterious, emerging | Feedback burn + particles |
| 2. Mitosis | 10s | Expanding, multiplying | Replicator instancing |
| 3. Forge | 14s | Technical, flowing | Phong spheres + CHOP trails |
| 4. Social | 16s | Chaotic, vibrant | Tunnel geometry + chromatic aberration |
| 5. Theater | 14s | Cinematic, emotional | 3D environment + screen glow |
| 6. Infinite | 13s | Epic, conclusive | Extruded text + neural rings |

---

## Pro Tips

- **No TD?** You can render each scene as a standalone `.toe` file. Just run one scene script at a time in a fresh project.
- **Music sync:** The Social Velocity scene (4) works great with a drop/beat. Set your music track and time the camera shake to the BPM.
- **4K:** Change all `resolutionw=1920` to `3840` and `resolutionh=1080` to `2160` in the scripts before building.
- **Color grade:** The ffmpeg script uses CRF 16 (visually lossless). For final delivery, you might want to add a LUT in the ffmpeg step.

---

## Differences from Video Kit v1

| v1 (Promo) | v2 (Cinema) |
|------------|-------------|
| Clean, UI-focused | Dark, abstract, cinematic |
| Shows the app literally | Shows the app's *effect* metaphorically |
| p5.js transitions | TouchDesigner 3D pipeline |
| Static explanation | Emotional journey |
| Good for README/landing | Good for stage/demo/hackathon |
