# Cinesmith Promo Video — Soundtrack Prompts

> Use these with **AudioCraft-audio-generation** or **audiocraft** skill.
> Each segment is designed to match a specific part of the 90-second promo.

---

## Segment 1: "The Brief" (0:00–0:15)
**Mood:** Tension, anticipation, machinery waking up

```
Cinematic dark ambient, low mechanical drones and sub-bass rumbles,
data processing sounds, subtle electronic ticks and beeps like a server farm
booting up, cyberpunk atmosphere, vast empty space, tension building,
no melody, purely atmospheric, 30 seconds, 320kbps
```

**AudioCraft params:**
- `model`: musicgen-large
- `duration`: 15
- `top_k`: 250
- `top_p`: 0.0
- `temperature`: 1.0
- `cfg_coef`: 3.0

---

## Segment 2: "The Memory Graph" (0:15–0:50)
**Mood:** Ethereal, crystalline, intelligent, pulsing

```
Ethereal ambient electronic music, crystalline synthesizer pads
resembling glass harmonica, subtle pulsing bass in 4/4 time at 90 BPM,
shimmering high-frequency textures like light refracting through crystal,
cyberpunk meditation, vast neural network consciousness, intelligent beauty,
no drums, purely atmospheric with gentle pulse, 40 seconds
```

**AudioCraft params:**
- `model`: musicgen-large
- `duration`: 35
- `top_k`: 250
- `top_p`: 0.0
- `temperature`: 1.0
- `cfg_coef`: 3.0

---

## Segment 3: "The Provenance" (0:50–1:05)
**Mood:** Clean, technical, confident, human

```
Clean minimal electronic track, precise arpeggiated synthesizer
at 100 BPM, confident and professional mood, subtle bass groove,
shimmering digital textures, modern tech documentary soundtrack,
sense of clarity and accountability, precision engineering, 20 seconds
```

**AudioCraft params:**
- `model`: musicgen-large
- `duration`: 15
- `top_k`: 250
- `top_p`: 0.0
- `temperature`: 0.9
- `cfg_coef`: 3.0

---

## Segment 4: "Remediation" (1:05–1:20)
**Mood:** Dissonance resolving to harmony, struggle then triumph

```
Dramatic cinematic electronic, initial dissonance with detuned
synths and glitchy textures that gradually resolve into pure consonant
chords, emotional journey from failure to success, cyberpunk orchestral,
synthesizer strings, rising energy, triumphant resolution, 20 seconds
```

**AudioCraft params:**
- `model`: musicgen-large
- `duration`: 15
- `top_k`: 250
- `top_p`: 0.0
- `temperature`: 1.1
- `cfg_coef`: 3.0

---

## Segment 5: "The Close" (1:20–1:30)
**Mood:** Triumphant, definitive, memorable

```
Triumphant cinematic synthwave finale, powerful bass drone
with soaring lead synthesizer melody, epic scale, sense of completion,
modern tech anthem, clean and bold, memorable hook, final chord
resolves to pure sub-bass, 15 seconds
```

**AudioCraft params:**
- `model`: musicgen-large
- `duration`: 10
- `top_k`: 250
- `top_p`: 0.0
- `temperature`: 1.0
- `cfg_coef`: 3.0

---

## Alternative: Single Continuous Track

If you prefer one generated track instead of segments:

```
Cinematic cyberpunk ambient electronic soundtrack, 90 seconds,
building from dark tension through ethereal crystalline beauty
to triumphant resolution, subtle pulsing rhythm, synthesizer pads,
glass harmonica textures, vast space, intelligent atmosphere,
no drums until the final 20 seconds, documentary score quality
```

---

## Technical Notes

### Using AudioCraft Skill in Hermes:
```
Load the audiocraft-audio-generation skill, then:

generate_music(
    description="<prompt above>",
    duration=15,
    output_path="/tmp/cinesmith_promo_seg1.wav"
)
```

### Using Suno (songwriting-and-ai-music skill):
If you want a vocal track, use the songwriting skill to write lyrics,
then generate with Suno using tags:
`[Verse]` / `[Chorus]` structure with cyberpunk electronic genre.

### Assembly:
After generating all segments, assemble with ffmpeg:
```bash
ffmpeg -i seg1.wav -i seg2.wav -i seg3.wav -i seg4.wav -i seg5.wav \
  -filter_complex "[0:a][1:a]crossfade=d=2[1x];[1x][2:a]crossfade=d=2[2x];[2x][3:a]crossfade=d=2[3x];[3x][4:a]crossfade=d=2[outa]" \
  -map "[outa]" -c:a pcm_s24le soundtrack.wav
```

### Sync with TouchDesigner:
Feed the final `soundtrack.wav` into TouchDesigner's AudioFileIn CHOP
for audio-reactive visuals. The skill docs have the exact signal chain:
```
AudioFileIn CHOP → AudioSpectrum CHOP (FFT=512, outlength=256)
→ Math CHOP (gain=10) → CHOP to TOP → GLSL TOP input
```
