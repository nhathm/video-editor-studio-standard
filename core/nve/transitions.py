"""Transitions between cuts.

Two families:
  cut effects   zoom-punch, flash, whip, glitch, shake: drawn at the cut point by the compose engine on top of
                the cut video; the cut itself stays a hard cut, so the length and every overlay time are unchanged.
  crossings     crossfade, slide-left, slide-up, zoom-in, wipe, circle: ffmpeg xfade at cut time. Only between
                two photos (a photo can be held longer on both sides, so the length still does not change);
                elsewhere they fall back to the closest cut effect.

Storyboard:
  tracks.video[i].transition   "<name>" | {"type": "<name>", "duration": s} | "none"; the transition INTO range i
  style.transition             default for every change of source ("<name>" | "random" | "none", default none).
                               Jump cuts inside the same source stay hard cuts unless a range names one.
"""
from __future__ import annotations

import random
import zlib

CUT_FX = {
    "zoom-punch": {"duration": 0.3, "label": {"vi": "Zoom giật", "en": "Zoom punch"},
                   "sfx": [{"asset": "lib:sfx/impact-bass-2", "at": 0.0, "volume": 0.22, "max": 0.7}]},
    "flash": {"duration": 0.24, "label": {"vi": "Chớp trắng", "en": "White flash"},
              "sfx": [{"asset": "lib:sfx/click-soft", "at": -0.02, "volume": 0.3}]},
    "whip": {"duration": 0.26, "label": {"vi": "Lia nhanh (whip)", "en": "Whip pan"},
             "sfx": [{"asset": "lib:sfx/whoosh", "at": -0.15, "volume": 0.35, "max": 0.6}]},
    "glitch": {"duration": 0.24, "label": {"vi": "Nhiễu (glitch)", "en": "Glitch"},
               "sfx": [{"asset": "lib:sfx/glitch-1", "at": -0.05, "volume": 0.3, "max": 0.5}]},
    "shake": {"duration": 0.36, "label": {"vi": "Rung", "en": "Shake"},
              "sfx": [{"asset": "lib:sfx/impact-bass-1", "at": 0.0, "volume": 0.2, "max": 0.7}]},
}
XFADE = {
    "crossfade": {"xfade": "fade", "duration": 0.5, "fallback": "flash", "label": {"vi": "Mờ chồng", "en": "Crossfade"}, "sfx": []},
    "slide-left": {"xfade": "slideleft", "duration": 0.4, "fallback": "whip", "label": {"vi": "Trượt ngang", "en": "Slide left"},
                   "sfx": [{"asset": "lib:sfx/whoosh-short", "at": -0.2, "volume": 0.3}]},
    "slide-up": {"xfade": "slideup", "duration": 0.4, "fallback": "whip", "label": {"vi": "Trượt lên", "en": "Slide up"},
                 "sfx": [{"asset": "lib:sfx/whoosh-short", "at": -0.2, "volume": 0.3}]},
    "zoom-in": {"xfade": "zoomin", "duration": 0.5, "fallback": "zoom-punch", "label": {"vi": "Zoom vào", "en": "Zoom in"},
                "sfx": [{"asset": "lib:sfx/whoosh-short", "at": -0.25, "volume": 0.3}]},
    "wipe": {"xfade": "wipeleft", "duration": 0.4, "fallback": "whip", "label": {"vi": "Gạt ngang", "en": "Wipe"},
             "sfx": [{"asset": "lib:sfx/whoosh-short", "at": -0.2, "volume": 0.25}]},
    "circle": {"xfade": "circleopen", "duration": 0.5, "fallback": "flash", "label": {"vi": "Mở tròn", "en": "Circle open"},
               "sfx": [{"asset": "lib:sfx/sparkle", "at": -0.1, "volume": 0.25}]},
}
ALL = {**CUT_FX, **XFADE}
RANDOM_CUT = ["zoom-punch", "flash", "whip", "glitch"]
RANDOM_PHOTO = ["crossfade", "slide-left", "slide-up", "zoom-in", "wipe"]


def catalog() -> list[dict]:
    return ([{"id": k, "kind": "cut-effect", "label": v["label"], "duration": v["duration"]} for k, v in CUT_FX.items()]
            + [{"id": k, "kind": "photo-crossing", "label": v["label"], "duration": v["duration"], "falls_back_to": v["fallback"]}
               for k, v in XFADE.items()])


def _norm(t) -> dict | None:
    if t is None:
        return None
    if isinstance(t, str):
        t = {"type": t}
    if not isinstance(t, dict) or not t.get("type") or t["type"] == "none":
        return {"type": "none"}
    return dict(t)


def resolve(sb: dict, segs: list[dict]) -> tuple[list[dict], list[str]]:
    """One entry per cut that gets a transition: {"i" (range it leads into), "at" (output time of the cut), "type",
    "family" ("cut" | "xfade"), "duration", "xfade" (ffmpeg name), "sfx"}. `segs` = timeline.segments(...) of
    sb.tracks.video. Returns (transitions, warnings)."""
    kinds = {s["id"]: s.get("kind", "video") for s in sb.get("sources", [])}
    default = _norm((sb.get("style") or {}).get("transition"))
    seed = zlib.crc32(str(sb.get("project", "")).encode())
    out, warns = [], []
    for i in range(1, len(segs)):
        a, b = segs[i - 1], segs[i]
        photos = kinds.get(a["src"]) == "image" and kinds.get(b["src"]) == "image"
        t = _norm(b.get("transition"))
        if t is None:
            if not default or default["type"] == "none" or a["src"] == b["src"]:
                continue
            t = dict(default)
        if t["type"] == "none":
            continue
        if t["type"] == "random":
            pool = RANDOM_PHOTO if photos else RANDOM_CUT
            t["type"] = random.Random(seed + i).choice(pool)
        name = t["type"]
        if name not in ALL:
            warns.append(f"tracks/video/{i}: unknown transition '{name}' (choose from {', '.join(ALL)}); hard cut used")
            continue
        if name in XFADE and not photos:
            fb = XFADE[name]["fallback"]
            warns.append(f"tracks/video/{i}: '{name}' only works between two photos; '{fb}' used instead")
            name = fb
        spec = ALL[name]
        d = float(t.get("duration") or spec["duration"])
        if name in XFADE:
            d = min(d, a["out_dur"] * 0.8, b["out_dur"] * 0.8)
        else:
            d = min(d, a["out_dur"], b["out_dur"], 0.8)
        out.append({"i": i, "at": round(b["out_start"], 3), "type": name, "family": "xfade" if name in XFADE else "cut",
                    "duration": round(max(0.08, d), 3), "xfade": spec.get("xfade"), "sfx": spec["sfx"]})
    return out, warns
