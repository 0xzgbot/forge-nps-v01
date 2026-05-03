#!/bin/bash
# Forge NPS — Screenshot Capture Helper
# ======================================
#
# Captures screenshots of your running dashboard for the hackathon posts.
# Outputs to: /Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets/
#
# Prerequisites:
#   - Dashboard running on http://127.0.0.1:7000
#   - At least one campaign completed (for shot data)
#   - Safari/Chrome open to the dashboard

OUTDIR="/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/assets"
mkdir -p "$OUTDIR"

echo "Forge NPS Screenshot Capture"
echo "============================"
echo ""
echo "This script will capture 5 screenshots using macOS screencapture."
echo "Make sure your dashboard is running and visible."
echo ""

read -p "Press ENTER when Settings page is visible..."
screencapture -x "$OUTDIR/screenshot_settings.png"
echo "✓ Settings captured"

read -p "Press ENTER when Event Stream is running (mid-campaign)..."
screencapture -x "$OUTDIR/screenshot_event_stream.png"
echo "✓ Event stream captured"

read -p "Press ENTER when Shot Detail (provenance) is open..."
screencapture -x "$OUTDIR/screenshot_shot_provenance.png"
echo "✓ Shot provenance captured"

read -p "Press ENTER when Retry Lineage is visible..."
screencapture -x "$OUTDIR/screenshot_retry_lineage.png"
echo "✓ Retry lineage captured"

read -p "Press ENTER when Memory Health JSON is visible..."
screencapture -x "$OUTDIR/screenshot_memory_health.png"
echo "✓ Memory health captured"

echo ""
echo "All screenshots saved to $OUTDIR"
ls -la "$OUTDIR"/screenshot_*.png
