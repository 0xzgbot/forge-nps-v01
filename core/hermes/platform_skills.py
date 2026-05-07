import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_LIBRARY_PATH = REPO_ROOT / "data" / "platform_skills" / "wholesome_audio_ideas.json"


TIKTOK_NEGATIONS = (
    "not tiktok",
    "no tiktok",
    "avoid tiktok",
    "not for tiktok",
    "do not make it tiktok",
    "don't make it tiktok",
)

TIKTOK_TRIGGERS = (
    "tiktok",
    "tik tok",
    "vertical short",
    "vertical video",
    "9:16",
    "9x16",
    "reels",
    "instagram reel",
    "youtube shorts",
    "short-form social",
    "short form social",
)

SERIES_TRIGGERS = (
    "series",
    "episode",
    "episodes",
    "same character",
    "recurring character",
    "girl next door",
    "consistent character",
    "character continuity",
)

WHOLESOME_TRIGGERS = (
    "happy",
    "wholesome",
    "heartwarming",
    "pixar",
    "travel",
    "girl next door",
    "sunlit",
    "soft pastel",
    "family friendly",
)

LOW_WATCH_TIME_TERMS = (
    "low watch-time",
    "low watch time",
    "watch-time risk",
    "watch time risk",
    "weak hook",
    "slow opening",
    "low retention",
    "retention risk",
    "boring opening",
)


def _safe_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _load_audio_library() -> List[Dict[str, Any]]:
    try:
        data = json.loads(AUDIO_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    items = data.get("audio_ideas", []) if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


def detect_platform_skill(
    brief: str,
    *,
    requested_mode: str = "auto",
    series_continuity: Optional[bool] = None,
) -> Dict[str, Any]:
    text = _safe_text(brief)
    lower = text.lower()
    mode = (requested_mode or "auto").strip().lower()
    forced = mode in {"tiktok", "tiktok_vertical", "force_tiktok"}
    disabled = mode in {"off", "none", "disabled"}
    negated = _contains_any(lower, TIKTOK_NEGATIONS)
    detected = _contains_any(lower, TIKTOK_TRIGGERS) and not negated
    active = bool((forced or (mode == "auto" and detected)) and not disabled)

    platform: Dict[str, Any] = {
        "active": active,
        "id": "tiktok_vertical" if active else "",
        "label": "TikTok Vertical" if active else "No platform skill",
        "mode": mode,
        "forced": forced,
        "detected": detected,
        "negated": negated,
        "constraints": {},
        "caption_style": {},
        "hook_strategy": {},
        "audio_ideas": [],
        "skills": [],
        "series_continuity": False,
        "wholesome": _contains_any(lower, WHOLESOME_TRIGGERS),
        "summary": "No platform skill active.",
    }

    if not active:
        return platform

    auto_series = _contains_any(lower, SERIES_TRIGGERS)
    platform["series_continuity"] = bool(auto_series if series_continuity is None else series_continuity)
    platform["constraints"] = {
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "duration_min_sec": 8,
        "duration_max_sec": 15,
        "duration_default_sec": 12,
        "fps": 24,
        "safe_zone": "bottom third captions, keep faces above lower 22 percent",
    }
    platform["caption_style"] = {
        "placement": "bottom_third",
        "font_weight": "bold",
        "fill": "white",
        "outline": "black",
        "case": "sentence_or_title",
        "max_words": 9,
    }
    platform["hook_strategy"] = {
        "first_3_seconds": (
            "Open with a close human expression, visible destination/payoff, or emotionally clear surprise. "
            "Keep motion readable on a phone and make the first caption understandable without sound."
        ),
        "shot_energy": "smiling close-up or immediate travel reveal before wider context",
        "remediation": viral_hook_remediation_text(),
    }
    platform["audio_ideas"] = _load_audio_library()[:6]
    platform["skills"] = [
        "tiktok_vertical_platform",
        "heartwarming_storytelling",
        "sunlit_travel_cinematography",
        "soft_pastel_animation_lighting",
    ]
    if "girl next door" in lower:
        platform["skills"].append("girl_next_door_realism")
    if "pixar" in lower or "animation" in lower:
        platform["skills"].append("pixar_specialist")
    if platform["series_continuity"]:
        platform["skills"].append("character_consistency")
    platform["summary"] = "TikTok vertical skill active: 1080x1920, 9:16, 8-15s, hook-first, caption-safe."
    return platform


def platform_prompt_clause(platform: Dict[str, Any]) -> str:
    if not platform or not platform.get("active"):
        return ""
    constraints = platform.get("constraints") or {}
    caption = platform.get("caption_style") or {}
    hook = platform.get("hook_strategy") or {}
    parts = [
        "platform skill: TikTok vertical short",
        f"output: {constraints.get('width', 1080)}x{constraints.get('height', 1920)} 9:16 vertical",
        f"duration target: {constraints.get('duration_min_sec', 8)}-{constraints.get('duration_max_sec', 15)} seconds",
        "first 0-3s: " + _safe_text(hook.get("first_3_seconds")),
        (
            "caption overlay: big readable "
            f"{caption.get('fill', 'white')} text with {caption.get('outline', 'black')} outline, "
            f"{caption.get('placement', 'bottom_third').replace('_', ' ')}, max {caption.get('max_words', 9)} words"
        ),
        "mobile framing: strong center subject, clear silhouette, no important details at extreme edges",
    ]
    if platform.get("series_continuity"):
        parts.append("series continuity: lock the same main character identity, wardrobe signature, face shape, and warmth across all shots")
    if platform.get("wholesome"):
        parts.append("tone: wholesome, optimistic, happy, emotionally legible, sunlit travel warmth")
    return "; ".join([p for p in parts if p])


def enrich_brief_with_platform(brief: str, platform: Dict[str, Any]) -> str:
    clause = platform_prompt_clause(platform)
    if not clause:
        return brief
    return f"{brief}\n\nPlatform constraints:\n{clause}"


def generate_hook_ideas(brief: str, platform: Optional[Dict[str, Any]] = None, limit: int = 5) -> List[Dict[str, str]]:
    text = _safe_text(brief)
    subject = text[:90].rstrip(".") or "this moment"
    audio = _load_audio_library()
    hooks = [
        {
            "hook": "Wait until you see where she ends up.",
            "caption": "Wait for the view",
            "audio": audio[0]["name"] if audio else "warm acoustic travel bed",
        },
        {
            "hook": "This tiny moment turned into the whole trip.",
            "caption": "The moment it changed",
            "audio": audio[1]["name"] if len(audio) > 1 else "soft piano emotional reveal",
        },
        {
            "hook": "POV: you finally find the place that feels like you.",
            "caption": "Found the feeling",
            "audio": audio[2]["name"] if len(audio) > 2 else "dreamy synth sparkle",
        },
        {
            "hook": "She almost missed the best part.",
            "caption": "Almost missed this",
            "audio": audio[3]["name"] if len(audio) > 3 else "upbeat handclap pop",
        },
        {
            "hook": f"A vertical travel short about {subject}.",
            "caption": "Save this feeling",
            "audio": audio[4]["name"] if len(audio) > 4 else "gentle cinematic swell",
        },
    ]
    return hooks[: max(1, int(limit or 5))]


def viral_hook_remediation_text() -> str:
    return (
        "Raise first-3-second retention: start closer on the main face or destination reveal, add a smile or "
        "clear emotional reaction, increase opening motion energy, simplify the first caption to under nine words, "
        "and show the payoff before the wide establishing shot."
    )


def review_flags_low_watch_time(review: Dict[str, Any]) -> bool:
    if not isinstance(review, dict):
        return False
    chunks: List[str] = []
    for key in ("status", "director_notes", "summary", "feedback"):
        chunks.append(_safe_text(review.get(key)))
    for key in ("coverage_gaps", "continuity_risks", "renderability_risks", "viral_risks", "watch_time_risks"):
        val = review.get(key)
        if isinstance(val, list):
            chunks.extend(_safe_text(x) for x in val)
        elif isinstance(val, dict):
            chunks.append(json.dumps(val, ensure_ascii=True))
        else:
            chunks.append(_safe_text(val))
    return _contains_any(" ".join(chunks), LOW_WATCH_TIME_TERMS)


def apply_viral_hook_remediation_to_first_shot(shots: List[Dict[str, Any]]) -> bool:
    if not shots:
        return False
    first = shots[0]
    addition = viral_hook_remediation_text()
    visual = _safe_text(first.get("visual_brief"))
    constraints = _safe_text(first.get("constraints"))
    if addition.lower() not in f"{visual} {constraints}".lower():
        first["visual_brief"] = f"{visual} Opening hook revision: {addition}".strip()
        first["constraints"] = f"{constraints}; first three seconds must carry retention hook energy".strip("; ")
        first["viral_hook_remediated"] = True
        return True
    return False


def carousel_caption_text(brief: str, platform: Optional[Dict[str, Any]] = None) -> str:
    hooks = generate_hook_ideas(brief, platform, limit=3)
    lines = ["Caption options:"]
    for idx, item in enumerate(hooks, start=1):
        lines.append(f"{idx}. {item['hook']}")
    lines.extend(
        [
            "",
            "Posting notes:",
            "- Use vertical 9:16 crops for TikTok/Reels/Shorts.",
            "- Keep the first visible caption under nine words.",
            "- Put the strongest still first, then the highest-motion clip second.",
        ]
    )
    return "\n".join(lines)
