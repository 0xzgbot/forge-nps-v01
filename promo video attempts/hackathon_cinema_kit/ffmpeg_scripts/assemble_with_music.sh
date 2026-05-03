#!/bin/bash
# Forge Cinema Kit — Post-Production Assembly
# Stitches scene renders together with transitions and optional music.

set -e

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RENDER_DIR="$KIT_DIR/assets/render"
OUTPUT_DIR="$KIT_DIR/assets/final"
mkdir -p "$OUTPUT_DIR"

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
FPS=30
RES="1920x1080"
CODEC="libx264"
CRF=16          # High quality (lower = better, 16-18 is visually lossless)
PRESET="slow"   # Compression efficiency
PIX_FMT="yuv420p"

# Scene files (render these from TouchDesigner first)
SCENE_SPARK="$RENDER_DIR/scene_spark.mp4"      # 0-8s
SCENE_MITOSIS="$RENDER_DIR/scene_mitosis.mp4"  # 8-18s
SCENE_FORGE="$RENDER_DIR/scene_forge.mp4"      # 18-32s
SCENE_SOCIAL="$RENDER_DIR/scene_social.mp4"    # 32-48s
SCENE_THEATER="$RENDER_DIR/scene_theater.mp4"  # 48-62s
SCENE_INFINITE="$RENDER_DIR/scene_infinite.mp4"# 62-75s

# Optional music track
MUSIC_TRACK=""  # Set to path: MUSIC_TRACK="$KIT_DIR/assets/music/hero_track.mp3"

FINAL_OUTPUT="$OUTPUT_DIR/forge_cinema_v2_master.mp4"

# ------------------------------------------------------------------
# Check inputs
# ------------------------------------------------------------------
check_file() {
    if [ ! -f "$1" ]; then
        echo "WARNING: Missing scene render: $1"
        echo "Render this scene from TouchDesigner before assembly."
        return 1
    fi
    return 0
}

# Build scene list for concat
declare -a SCENE_LIST
SCENE_LIST+=("$SCENE_SPARK")
SCENE_LIST+=("$SCENE_MITOSIS")
SCENE_LIST+=("$SCENE_FORGE")
SCENE_LIST+=("$SCENE_SOCIAL")
SCENE_LIST+=("$SCENE_THEATER")
SCENE_LIST+=("$SCENE_INFINITE")

# Validate all scenes exist
ALL_PRESENT=true
for f in "${SCENE_LIST[@]}"; do
    check_file "$f" || ALL_PRESENT=false
done

if [ "$ALL_PRESENT" = false ]; then
    echo ""
    echo "Some scene renders are missing. Options:"
    echo "  1. Render all scenes from TD first, then re-run this script."
    echo "  2. Use the placeholder concat list below and comment out missing scenes."
    echo ""
fi

# ------------------------------------------------------------------
# Method 1: Direct concat (no transitions) — fastest
# ------------------------------------------------------------------
echo "Building concat list..."
CONCAT_LIST="$OUTPUT_DIR/concat_list.txt"
> "$CONCAT_LIST"
for f in "${SCENE_LIST[@]}"; do
    if [ -f "$f" ]; then
        echo "file '$f'" >> "$CONCAT_LIST"
    fi
done

echo "Assembling final video (direct concat)..."
ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" \
    -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
    -movflags +faststart \
    -an \
    "$OUTPUT_DIR/forge_cinema_v2_no_music.mp4"

echo ""
echo "✅ Assembled: $OUTPUT_DIR/forge_cinema_v2_no_music.mp4"

# ------------------------------------------------------------------
# Method 2: With crossfade transitions (requires all scenes)
# ------------------------------------------------------------------
if [ "$ALL_PRESENT" = true ]; then
    echo ""
    echo "Building crossfade version..."
    
    # Crossfade duration in seconds
    XFADE=0.5
    
    # Complex filtergraph for crossfades between 6 scenes
    # This gets complex fast; using a simpler approach with intermediate files
    
    TMP_DIR="$OUTPUT_DIR/tmp"
    mkdir -p "$TMP_DIR"
    
    # Crossfade scene 1→2
    ffmpeg -y -i "$SCENE_SPARK" -i "$SCENE_MITOSIS" \
        -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=7.5[vt1]" \
        -map "[vt1]" -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
        "$TMP_DIR/part_01_02.mp4"
    
    # Crossfade result → scene 3
    ffmpeg -y -i "$TMP_DIR/part_01_02.mp4" -i "$SCENE_FORGE" \
        -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=16.5[vt2]" \
        -map "[vt2]" -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
        "$TMP_DIR/part_01_03.mp4"
    
    # Crossfade result → scene 4
    ffmpeg -y -i "$TMP_DIR/part_01_03.mp4" -i "$SCENE_SOCIAL" \
        -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=30.5[vt3]" \
        -map "[vt3]" -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
        "$TMP_DIR/part_01_04.mp4"
    
    # Crossfade result → scene 5
    ffmpeg -y -i "$TMP_DIR/part_01_04.mp4" -i "$SCENE_THEATER" \
        -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=46.5[vt4]" \
        -map "[vt4]" -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
        "$TMP_DIR/part_01_05.mp4"
    
    # Crossfade result → scene 6
    ffmpeg -y -i "$TMP_DIR/part_01_05.mp4" -i "$SCENE_INFINITE" \
        -filter_complex "[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=60.5[vt5]" \
        -map "[vt5]" -c:v $CODEC -crf $CRF -preset $PRESET -pix_fmt $PIX_FMT \
        -movflags +faststart \
        -an \
        "$OUTPUT_DIR/forge_cinema_v2_crossfade.mp4"
    
    echo "✅ Crossfade version: $OUTPUT_DIR/forge_cinema_v2_crossfade.mp4"
    
    # Cleanup temp
    rm -rf "$TMP_DIR"
fi

# ------------------------------------------------------------------
# Method 3: With music bed
# ------------------------------------------------------------------
if [ -n "$MUSIC_TRACK" ] && [ -f "$MUSIC_TRACK" ]; then
    echo ""
    echo "Adding music bed..."
    
    # Use crossfade version if available, else direct concat
    VIDEO_INPUT="$OUTPUT_DIR/forge_cinema_v2_crossfade.mp4"
    [ -f "$VIDEO_INPUT" ] || VIDEO_INPUT="$OUTPUT_DIR/forge_cinema_v2_no_music.mp4"
    
    ffmpeg -y -i "$VIDEO_INPUT" -i "$MUSIC_TRACK" \
        -filter_complex "[1:a]afade=t=out:st=65:d=5,volume=0.25[a]" \
        -map 0:v -map "[a]" \
        -c:v copy -c:a aac -b:a 320k \
        -movflags +faststart \
        -shortest \
        "$FINAL_OUTPUT"
    
    echo "✅ FINAL MASTER: $FINAL_OUTPUT"
else
    echo ""
    echo "No music track provided. To add music, set MUSIC_TRACK and re-run."
    echo "Example: MUSIC_TRACK=\"$KIT_DIR/assets/music/my_track.mp3\" ./assemble_with_music.sh"
fi

echo ""
echo "============================================"
echo "  Forge Cinema Kit — Assembly Complete"
echo "============================================"
echo "Output directory: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"/*.mp4 2>/dev/null || true
