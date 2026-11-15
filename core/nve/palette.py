"""Text colours (style.palette) from a reference picture, from one colour the user names, or chosen automatically
so the accent stands out from the footage.

palette keys: ink (stroke / box behind text, dark), accent (highlighted words, hook marker), text (normal words),
spoken (karaoke words already said)."""
from __future__ import annotations

import colorsys
from pathlib import Path

DEFAULT = {"ink": "#1F2A44", "accent": "#FFD84D", "text": "#FFFFFF", "spoken": "#9EE6FF"}
# accents that read well on video, with the hue (degrees) used to keep away from the footage's own colours
ACCENTS = [("#FFD84D", 48, "warm yellow"), ("#C6FF3D", 80, "lime"), ("#3DE0FF", 190, "cyan"),
           ("#FF4FA3", 330, "hot pink"), ("#FF8A1F", 28, "orange"), ("#B388FF", 265, "lilac")]
SKIN_HUE = 25


def _rgb(hx: str) -> tuple[int, int, int]:
    h = hx.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02X}" for c in rgb)


def luminance(hx: str) -> float:
    def ch(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hx)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(hx: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in _rgb(hx))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(h: float, l: float, s: float) -> str:
    return _hex(c * 255 for c in colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s))))


def ink_for(accent: str) -> str:
    """A very dark shade of the accent's hue: reads as 'designed', and white/accent text on it passes contrast."""
    h, _, s = _hls(accent)
    ink = _from_hls(h, 0.14, min(0.55, s))
    return ink if contrast(ink, "#FFFFFF") >= 7 else "#111111"


def spoken_for(accent: str) -> str:
    h, _, _ = _hls(accent)
    return _from_hls(h + 0.5, 0.82, 0.85)   # light complement: says 'already said' without fighting the accent


def make(accent: str, ink: str | None = None) -> dict:
    accent = _hex(_rgb(accent))
    h, l, s = _hls(accent)
    if luminance(accent) < 0.1:   # a very dark brand colour cannot be a text highlight on video: lighten it
        accent = _from_hls(h, max(l, 0.55), max(s, 0.75))
    ink = ink or ink_for(accent)
    # captions and titles are large and bold: WCAG asks 3:1 there
    if contrast(ink, accent) < 3:
        ink = "#111111"
    while contrast(ink, accent) < 3:
        h, l, s = _hls(accent)
        accent = _from_hls(h, l + 0.04, s)
    return {"ink": ink, "accent": accent, "text": "#FFFFFF", "spoken": spoken_for(accent)}


def dominant(img_path: Path, k: int = 6) -> list[dict]:
    """Main colours of a picture, biggest share first: [{"hex", "share", "saturation", "lightness"}]."""
    from PIL import Image
    im = Image.open(img_path).convert("RGB")
    im.thumbnail((200, 200))
    q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: 3 * k]
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts) or 1
    out = []
    for c, idx in counts:
        hx = _hex(pal[3 * idx: 3 * idx + 3])
        _, l, s = _hls(hx)
        out.append({"hex": hx, "share": round(c / total, 3), "saturation": round(s, 2), "lightness": round(l, 2)})
    return out


def from_image(img_path: Path) -> dict:
    """Accent = the most vivid colour that covers a real part of the picture; ink = its darkest colour when dark
    enough, else a dark shade of the accent."""
    cols = dominant(img_path)
    vivid = [c for c in cols if c["share"] >= 0.03 and 0.2 < c["lightness"] < 0.9]
    acc = max(vivid or cols, key=lambda c: c["saturation"] * (0.5 + c["share"]))["hex"]
    darkest = min(cols, key=lambda c: c["lightness"])
    ink = darkest["hex"] if darkest["lightness"] < 0.2 and contrast(darkest["hex"], "#FFFFFF") >= 7 else None
    pal = make(acc, ink)
    return {"palette": pal, "colours": cols, "how": "from the reference picture"}


def _hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def auto(frames: list[Path]) -> dict:
    """Pick the accent whose hue is furthest from the footage's main colours (and from skin), so highlights pop."""
    hues: list[tuple[float, float]] = []
    for f in frames:
        for c in dominant(f):
            if c["saturation"] > 0.25 and 0.15 < c["lightness"] < 0.85:
                h, _, _ = _hls(c["hex"])
                hues.append((h * 360, c["share"]))
    best, best_score = ACCENTS[0], -1.0
    for acc in ACCENTS:
        near = sum(w for h, w in hues if _hue_dist(h, acc[1]) < 40)
        score = 1.0 - near + (0.15 if _hue_dist(acc[1], SKIN_HUE) > 30 else 0) + (0.05 if acc is ACCENTS[0] else 0)
        if score > best_score:
            best, best_score = acc, score
    pal = make(best[0])
    if best[0] == DEFAULT["accent"]:
        pal = dict(DEFAULT)
    return {"palette": pal, "how": f"automatic: {best[2]} stands out from the footage's own colours"}
