#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# Forge NPS — Promo Video Assembly Script
# ═══════════════════════════════════════════════════════════════════════════
#
# This script stitches together all the promo video components into a
# final 90-second film. Run this after you've generated all assets.
#
# PREREQUISITES (for you to verify):
#   - ffmpeg installed: brew install ffmpeg
#   - All source files exist (see paths below)
#   - TouchDesigner video exported as ProRes MOV
#
# USAGE:
#   chmod +x assemble_promo.sh
#   ./assemble_promo.sh
#
# OUTPUT:
#   /tmp/forge_nps_promo_final.mov  (ProRes HQ, 1280x720, 30fps)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
OUTPUT_DIR="/tmp"
FINAL_OUTPUT="${OUTPUT_DIR}/forge_nps_promo_final.mov"
TEMP_DIR="${OUTPUT_DIR}/forge_promo_temp"
FPS=30
RESOLUTION="1280x720"

# Source files (UPDATE THESE PATHS to match your actual exports)
DASHBOARD_RECORDING="${TEMP_DIR}/dashboard_recording.mov"      # YOU record this
TD_VIDEO="/tmp/forge_memory_graph_output.mov"                  # TouchDesigner output
TRANSITION1_FRAMES="${TEMP_DIR}/transition1_frames/frame_%06d.png"  # p5js export
TRANSITION2_FRAMES="${TEMP_DIR}/transition2_frames/frame_%06d.png"  # p5js export
TRANSITION3_FRAMES="${TEMP_DIR}/transition3_frames/frame_%06d.png"  # p5js export
HERO1="${TEMP_DIR}/hero_director.png"
HERO2="${TEMP_DIR}/hero_engineer.png"
HERO3="${TEMP_DIR}/hero_renderer.png"
HERO4="${TEMP_DIR}/hero_gate.png"
HERO5="${TEMP_DIR}/hero_memory.png"
HERO6="${TEMP_DIR}/hero_output.png"
SOUNDTRACK="${TEMP_DIR}/soundtrack.wav"

# Timing (in seconds)
T_OPEN=5
T_DASHBOARD=10
T_TD=20
T_TRANSITION1=5
T_HERO1=3
T_HERO2=3
T_HERO3=3
T_TRANSITION2=5
T_HERO4=3
T_HERO5=3
T_HERO6=3
T_TRANSITION3=8
T_CLOSE=5

echo "═══════════════════════════════════════════════════════════════"
echo "  Forge NPS — Promo Video Assembly"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Validate prerequisites ────────────────────────────────────────────────

if ! command -v ffmpeg &> /dev/null; then
    echo "[ERROR] ffmpeg not found. Install it:"
    echo "  brew install ffmpeg"
    exit 1
fi

mkdir -p "${TEMP_DIR}"

# ── Helper: Create colored bars with text ─────────────────────────────────

generate_opening() {
    echo "[1/12] Generating opening title..."
    ffmpeg -y -f lavfi -i "color=c=black:s=${RESOLUTION}:r=${FPS}:d=${T_OPEN}" \
        -vf "
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='EVERY PIXEL HAS AN ORIGIN':
            fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-30:
            enable='between(t,0.5,4)':
            alpha='if(lt(t,1),t-0.5,if(lt(t,3.5),1,4-t))',
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='Forge NPS':
            fontsize=72:fontcolor=#00FFFF:x=(w-text_w)/2:y=(h-text_h)/2+40:
            enable='between(t,1,4)':
            alpha='if(lt(t,1.5),t-1,if(lt(t,3.5),1,4-t))',
            noise=alls=20:allf=t+u,
            format=yuv420p
        " \
        -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
        "${TEMP_DIR}/opening.mov" 2>/dev/null
}

# ── Helper: Create closing title ──────────────────────────────────────────

generate_closing() {
    echo "[2/12] Generating closing title..."
    ffmpeg -y -f lavfi -i "color=c=black:s=${RESOLUTION}:r=${FPS}:d=${T_CLOSE}" \
        -vf "
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='Forge NPS':
            fontsize=96:fontcolor=#00FFFF:x=(w-text_w)/2:y=(h-text_h)/2-50:
            enable='between(t,0.5,4)':
            alpha='if(lt(t,1),t-0.5,if(lt(t,3.5),1,4.5-t))',
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='Every shot, accounted for.':
            fontsize=36:fontcolor=#8B949E:x=(w-text_w)/2:y=(h-text_h)/2+50:
            enable='between(t,1.5,4)':
            alpha='if(lt(t,2),t-1.5,if(lt(t,3.5),1,4.5-t))',
            format=yuv420p
        " \
        -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
        "${TEMP_DIR}/closing.mov" 2>/dev/null
}

# ── Helper: Render p5js transitions to video ──────────────────────────────

render_transition() {
    local name=$1
    local frames=$2
    local duration=$3
    local output="${TEMP_DIR}/${name}.mov"

    echo "[ ] Rendering ${name}..."

    if [ -f "${frames/frame_%06d.png/000001.png}" ]; then
        ffmpeg -y -framerate ${FPS} -i "${frames}" \
            -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
            -t ${duration} \
            "${output}" 2>/dev/null
    else
        echo "[WARN] ${name} frames not found. Creating placeholder."
        ffmpeg -y -f lavfi -i "color=c=#0A0E14:s=${RESOLUTION}:r=${FPS}:d=${duration}" \
            -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
            "${output}" 2>/dev/null
    fi
}

# ── Helper: Convert hero frames to video clips ────────────────────────────

hero_to_clip() {
    local input=$1
    local duration=$2
    local output=$3

    if [ -f "${input}" ]; then
        ffmpeg -y -loop 1 -i "${input}" -t ${duration} -framerate ${FPS} \
            -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
            -vf "zoompan=z='min(zoom+0.0015,1.15)':d=${duration}*${FPS}:s=${RESOLUTION}:fps=${FPS},format=yuv420p" \
            "${output}" 2>/dev/null
    else
        echo "[WARN] Hero frame ${input} not found. Creating placeholder."
        ffmpeg -y -f lavfi -i "color=c=#0A0E14:s=${RESOLUTION}:r=${FPS}:d=${duration}" \
            -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
            "${output}" 2>/dev/null
    fi
}

# ── Build all segments ────────────────────────────────────────────────────

echo "Building segments..."
echo ""

generate_opening
generate_closing

render_transition "transition1" "${TRANSITION1_FRAMES}" ${T_TRANSITION1}
render_transition "transition2" "${TRANSITION2_FRAMES}" ${T_TRANSITION2}
render_transition "transition3" "${TRANSITION3_FRAMES}" ${T_TRANSITION3}

hero_to_clip "${HERO1}" ${T_HERO1} "${TEMP_DIR}/hero1_clip.mov"
hero_to_clip "${HERO2}" ${T_HERO2} "${TEMP_DIR}/hero2_clip.mov"
hero_to_clip "${HERO3}" ${T_HERO3} "${TEMP_DIR}/hero3_clip.mov"
hero_to_clip "${HERO4}" ${T_HERO4} "${TEMP_DIR}/hero4_clip.mov"
hero_to_clip "${HERO5}" ${T_HERO5} "${TEMP_DIR}/hero5_clip.mov"
hero_to_clip "${HERO6}" ${T_HERO6} "${TEMP_DIR}/hero6_clip.mov"

# Dashboard placeholder (YOU need to record this)
if [ -f "${DASHBOARD_RECORDING}" ]; then
    echo "[OK] Using dashboard recording"
else
    echo "[WARN] Dashboard recording not found. Creating placeholder."
    ffmpeg -y -f lavfi -i "color=c=#0D1117:s=${RESOLUTION}:r=${FPS}:d=${T_DASHBOARD}" \
        -vf "
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='[RECORD DASHBOARD FOOTAGE HERE]':
            fontsize=32:fontcolor=#00FFFF:x=(w-text_w)/2:y=(h-text_h)/2:
            format=yuv420p
        " \
        -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
        "${TEMP_DIR}/dashboard.mov" 2>/dev/null
    DASHBOARD_RECORDING="${TEMP_DIR}/dashboard.mov"
fi

# TouchDesigner placeholder
if [ -f "${TD_VIDEO}" ]; then
    echo "[OK] Using TouchDesigner output"
else
    echo "[WARN] TouchDesigner video not found. Creating placeholder."
    ffmpeg -y -f lavfi -i "color=c=black:s=${RESOLUTION}:r=${FPS}:d=${T_TD}" \
        -vf "
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:
            text='[TOUCHDESIGNER OUTPUT HERE]':
            fontsize=32:fontcolor=#BD00FF:x=(w-text_w)/2:y=(h-text_h)/2:
            format=yuv420p
        " \
        -c:v prores -profile:v 3 -pix_fmt yuv422p10le \
        -t ${T_TD} \
        "${TEMP_DIR}/td_placeholder.mov" 2>/dev/null
    TD_VIDEO="${TEMP_DIR}/td_placeholder.mov"
fi

# ── Concatenate all segments ──────────────────────────────────────────────

echo ""
echo "[11/12] Concatenating segments..."

# Create concat list
cat > "${TEMP_DIR}/concat_list.txt" << EOF
file '${TEMP_DIR}/opening.mov'
file '${DASHBOARD_RECORDING}'
file '${TD_VIDEO}'
file '${TEMP_DIR}/transition1.mov'
file '${TEMP_DIR}/hero1_clip.mov'
file '${TEMP_DIR}/hero2_clip.mov'
file '${TEMP_DIR}/hero3_clip.mov'
file '${TEMP_DIR}/transition2.mov'
file '${TEMP_DIR}/hero4_clip.mov'
file '${TEMP_DIR}/hero5_clip.mov'
file '${TEMP_DIR}/hero6_clip.mov'
file '${TEMP_DIR}/transition3.mov'
file '${TEMP_DIR}/closing.mov'
EOF

ffmpeg -y -f concat -safe 0 -i "${TEMP_DIR}/concat_list.txt" \
    -c copy \
    "${TEMP_DIR}/promo_noaudio.mov"

# ── Add soundtrack ────────────────────────────────────────────────────────

echo "[12/12] Adding soundtrack..."

if [ -f "${SOUNDTRACK}" ]; then
    ffmpeg -y -i "${TEMP_DIR}/promo_noaudio.mov" -i "${SOUNDTRACK}" \
        -c:v copy -c:a pcm_s24le -shortest \
        "${FINAL_OUTPUT}"
else
    echo "[WARN] Soundtrack not found. Output will have no audio."
    cp "${TEMP_DIR}/promo_noaudio.mov" "${FINAL_OUTPUT}"
fi

# ── Done ──────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ASSEMBLY COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Output: ${FINAL_OUTPUT}"
echo ""

if command -v ffprobe &> /dev/null; then
    DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${FINAL_OUTPUT}" 2>/dev/null | cut -d. -f1)
    echo "Duration: ${DURATION}s"
fi

echo ""
echo "NEXT STEPS:"
echo "  1. Review ${FINAL_OUTPUT} in your video player"
echo "  2. If quality is good, convert to H.264 for sharing:"
echo "     ffmpeg -i ${FINAL_OUTPUT} -c:v libx264 -crf 18 -preset slow -c:a aac -b:a 192k ${OUTPUT_DIR}/forge_nps_promo_final.mp4"
echo "  3. Upload to YouTube/Vimeo for hackathon submission"
echo ""
