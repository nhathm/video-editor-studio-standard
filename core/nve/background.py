"""Backgrounds behind a keyed (green-screen) person.

style.background in the storyboard:
    {"type": "color", "color": "#F4F1EA"}
    {"type": "gradient", "colors": ["#E7EEFF", "#9FB6FF"], "angle": 160, "glow": true, "dots": true}
    {"type": "sections", "dots": true, "sections": [
        {"start": 0.0, "colors": ["#E7EEFF", "#9FB6FF"], "scale": 0.86},
        {"start": 4.1, "colors": ["#E3F9D9", "#8EDB8A"], "scale": 0.92}]}   # one look per part of the video
    {"type": "image", "asset": "assets/kitchen.jpg"}
style.person: {"scale": 0.9, "y": 0.0}   # person size (1 = full frame) and offset from the bottom (fraction of H)
"""
from __future__ import annotations

import math
from pathlib import Path

DEFAULT = {"type": "gradient", "colors": ["#E7EEFF", "#9FB6FF"], "angle": 160, "glow": True, "dots": True}


def layers(spec: dict | None, duration: float) -> list[dict]:
    """Normalise any background spec into time-stamped layers [{start, end, kind, ...}]."""
    spec = spec or DEFAULT
    t = spec.get("type", "gradient")
    base = {"glow": spec.get("glow", True), "angle": spec.get("angle", 160)}
    if t == "sections":
        secs = sorted(spec["sections"], key=lambda s: s["start"])
        out = []
        for i, s in enumerate(secs):
            end = secs[i + 1]["start"] if i + 1 < len(secs) else duration
            if "image" in s:
                out.append({**base, "start": s["start"], "end": end, "kind": "image", "asset": s["image"], "scale": s.get("scale")})
            else:
                out.append({**base, "start": s["start"], "end": end, "kind": "gradient",
                            "colors": s.get("colors") or [s.get("color", "#FFFFFF")] * 2, "scale": s.get("scale")})
        return out
    if t == "color":
        return [{**base, "start": 0, "end": duration, "kind": "gradient", "colors": [spec["color"]] * 2, "glow": False}]
    if t == "image":
        return [{**base, "start": 0, "end": duration, "kind": "image", "asset": spec["asset"]}]
    return [{**base, "start": 0, "end": duration, "kind": "gradient", "colors": spec.get("colors", DEFAULT["colors"])}]


def css(layer: dict, img_url: str | None = None) -> str:
    if layer["kind"] == "image":
        return f"background: url('{img_url}') center / cover no-repeat;"
    a, b = layer["colors"][0], layer["colors"][-1]
    glow = "radial-gradient(circle at 20% 12%, #ffffff 0%, rgba(255,255,255,0) 45%), " if layer.get("glow") else ""
    return f"background: {glow}linear-gradient({layer.get('angle', 160)}deg, {a} 0%, {b} 100%);"


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def png(layer: dict, W: int, H: int, out: Path, dots: bool, project_dir: Path | None = None) -> Path:
    """Render one layer as a PNG (for the ffmpeg/ASS engine)."""
    import numpy as np
    from PIL import Image, ImageDraw
    if layer["kind"] == "image":
        from nve import assets
        im = Image.open(assets.resolve(layer["asset"], project_dir)).convert("RGB")
        s = max(W / im.width, H / im.height)
        im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)))
        im = im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
    else:
        a, b = np.array(_rgb(layer["colors"][0]), np.float32), np.array(_rgb(layer["colors"][-1]), np.float32)
        ang = math.radians(layer.get("angle", 160))
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        dx, dy = math.sin(ang), -math.cos(ang)        # CSS: 0deg = towards top, clockwise
        proj = xx * dx + yy * dy
        tt = ((proj - proj.min()) / max(1e-6, proj.max() - proj.min()))[..., None]
        img = a * (1 - tt) + b * tt
        if layer.get("glow"):
            r = np.sqrt((xx - 0.2 * W) ** 2 + (yy - 0.12 * H) ** 2)
            g = np.clip(1 - r / (0.45 * math.hypot(W, H) / math.sqrt(2)), 0, 1)[..., None]
            img = img * (1 - g) + 255 * g
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if dots:
        d = ImageDraw.Draw(im, "RGBA")
        step, rad = int(46 * W / 1080), max(1, int(3 * W / 1080))
        for y in range(0, H, step):
            for x in range(0, W, step):
                d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=(255, 255, 255, 115))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
