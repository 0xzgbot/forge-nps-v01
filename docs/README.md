# Docs Directory

Primary operational docs live here so the repository root stays readable on GitHub:

- [README.md](../README.md)
- [PRODUCE.md](PRODUCE.md) — home app: prompt → 3090 boards → Spark H3 → cut
- [QUICKSTART.md](QUICKSTART.md) — connect four lights, Scout/Shoot, queue, cut
- [INSTALLATION_AGENT_GUIDE.md](INSTALLATION_AGENT_GUIDE.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [PIPELINE_CONTRACT_SUMMARY.md](PIPELINE_CONTRACT_SUMMARY.md)
- [CHANGELOG.md](CHANGELOG.md)
- [STABILITY_CHECKLIST.md](STABILITY_CHECKLIST.md)
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md)

Current refresh notes:

- [CHANGELOG.md](CHANGELOG.md) **2026-08-30**: Produce is `/`. Spark MiniMax H3 + dual 3090s, queue, Scout/Shoot, range retake, mute, color pass. `/studio` is legacy.
- Script Studio (legacy `/studio`) still supports one-click **Generate Videos** from a short prompt: package, coverage, storyboard start frames, and individual LTX clips.
- Storyboard image generation is model-selectable for local Spark/ComfyUI, OpenAI image generation, and Gemini/Nano Banana providers. Local output filenames use the selected model prefix.
