#!/bin/bash
# Forge NPS — Demo Video Recording Script
# ========================================
#
# Records your screen while you run through the demo script.
# Outputs: /Users/zgbot/Desktop/FORGE_NPS_MEDIA/forge_demo_video.mp4
#
# Usage:
#   1. Launch your dashboard: python3 -m dashboard.forge_dashboard
#   2. Open browser to http://127.0.0.1:7000
#   3. Run this script
#   4. Follow the on-screen timer and perform each demo step
#   5. Press Ctrl+C to stop recording

OUTPUT="/Users/zgbot/Desktop/FORGE_NPS_MEDIA/forge_demo_video.mp4"
mkdir -p "$(dirname "$OUTPUT")"

echo "========================================"
echo "Forge NPS Demo Recorder"
echo "========================================"
echo ""
echo "Output: $OUTPUT"
echo ""
echo "Steps to perform during recording:"
echo "  0:00  Show Settings page with connection tests"
echo "  0:10  Enter brief → click Run Campaign"
echo "  0:20  Narrate stream: profile → kimi → compiler → spark"
echo "  0:40  Open shot → scroll provenance"
echo "  1:00  Find failed shot → Re-Audit"
echo "  1:20  Remediate → show retry lineage"
echo "  1:40  Show Memory Health endpoint"
echo "  1:50  Show best renders / TouchDesigner clips"
echo "  2:00  Close with tagline"
echo ""
echo "Press ENTER to start recording (5 sec countdown)..."
read

# Countdown
for i in 5 4 3 2 1; do
    echo "Starting in $i..."
    sleep 1
done

echo "🔴 RECORDING STARTED"
echo "Press Ctrl+C to stop"

# Record screen using ffmpeg
# macOS: capture display 0 at 1920x1080, 30fps, with audio
ffmpeg -y \
    -f avfoundation \
    -i "1:none" \
    -pix_fmt yuv420p \
    -r 30 \
    -s 1920x1080 \
    -c:v libx264 \
    -crf 18 \
    -preset fast \
    "$OUTPUT"

echo ""
echo "✅ Recording saved to: $OUTPUT"
