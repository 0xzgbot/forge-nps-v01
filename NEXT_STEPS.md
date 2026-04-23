# FORGE NPS — Scope-Locked Action Plan

**Date:** 2026-04-23  
**Deadline:** May 3 (11 days)  
**Status:** MOCK MODE WORKS. Scope locked. No new features.

---

## 🚫 POST-HACKATHON ONLY (DO NOT TOUCH UNTIL MAY 4)

- ~~LTX 2.3 video pipeline~~
- ~~120-photo batch renders~~
- ~~Cosmos vision integration~~
- ~~VIME vector database~~
- ~~FP4 quantization~~
- ~~Mac app wrapper~~
- ~~Full website build~~
- ~~Audio agent / voice pipeline~~

---

## ✅ Hackathon MVP Checklist

| # | Task | Status | Owner |
|---|------|--------|-------|
| 1 | `demo.py --mock` runs end-to-end | ✅ | Done |
| 2 | `demo.py --mock --mock-failure` shows remediation loop | ✅ | Done |
| 3 | Memory consolidation records first-try successes | ✅ | Done |
| 4 | README.md explains the system | ✅ | Done |
| 5 | Real API smoke test (1 real shot) | ⬜ | You — add real `KIMI_API_KEY` and run |
| 6 | Dashboard polish | ⬜ | J11 — if time allows |
| 7 | Submission video / GIF walkthrough | ⬜ | Day 10–11 |

---

## 🔥 Immediate Next Actions (Today)

1. **Replace `dummy_key` in `.env`** with your real Kimi API key.
2. **Run one real shot:** `python3 demo.py --script scripts/demo/pilot_script.md`
3. **Fix whatever breaks.** Do not add features.
4. **Record a 2-minute demo** using `--mock-failure` so judges see the self-healing loop.

---

## Quick Commands

```bash
# Mock demo (no keys needed)
python3 demo.py --mock

# Mock demo with forced failure to show remediation
python3 demo.py --mock --mock-failure

# Memory learning showcase
python3 demo.py --memory-demo

# Real run (requires KIMI_API_KEY + ComfyUI)
python3 demo.py --script scripts/demo/pilot_script.md

# Dashboard
python3 demo.py --mock --dashboard
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| Real API fails on demo day | Medium | High | `--mock` and `--mock-failure` are demo lifelines |
| Memory stats look empty | Low | Low | Already fixed — first-try successes now log outcomes |
| Scope creep | High | Critical | **This document is the lock.** Read it when tempted to add video. |
