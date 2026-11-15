"""Storyboard + cut + words -> an engine-neutral render plan that every compose engine consumes.
Block defaults (props, default SFX) are applied here, so engines only draw."""
from __future__ import annotations

from pathlib import Path

from nve import assets, registry
from nve.paths import NveError
from nve.util import log


def _block(block_id: str, ws: Path | None) -> dict:
    return registry.resolve(block_id, "block", ws)


def _props(block: dict, given: dict) -> dict:
    out = {k: v.get("default") for k, v in block.get("props", {}).items() if isinstance(v, dict)}
    out.update(given or {})
    for k, v in block.get("props", {}).items():
        if isinstance(v, dict) and v.get("required") and not out.get(k):
            raise NveError(f"{block['id']}: prop '{k}' is required")
    return out


# words a caption line should not end on: they lean on the next word (break before them instead)
CONNECTORS = {"và", "của", "là", "thì", "mà", "những", "các", "một", "cho", "với", "để", "nhưng", "hay", "hoặc", "rất",
              "từ", "khi", "vì", "nếu", "the", "a", "an", "to", "of", "and", "for", "with", "in", "on", "but", "or"}


def rich(text: str) -> list[list[tuple[str, bool]]]:
    """'BẠN ĐANG *UỐNG SAI*|TRÀ SỮA' -> lines of (piece, emphasised). '|' = new line, *...* = accent colour."""
    out = []
    for line in str(text).split("|"):
        parts = line.split("*")
        out.append([(t, k % 2 == 1) for k, t in enumerate(parts) if t])
    return out


def plain(text: str) -> str:
    return str(text).replace("*", "")


def font_path(family: str) -> Path | None:
    """The heaviest static file of a pack family (what both engines draw titles with)."""
    from nve.paths import INSTALL_ROOT
    d = INSTALL_ROOT / "packs" / "fonts" / family.replace(" ", "")
    for style in ("Black", "Bold"):
        f = d / f"{family.replace(' ', '')}-{style}.ttf"
        if f.exists():
            return f
    files = sorted(d.glob("*.ttf")) if d.is_dir() else []
    return files[0] if files else None


def win_ratio(ff: Path) -> float:
    """(usWinAscent + usWinDescent) / unitsPerEm: libass treats a font size as this height, so an em of N px
    needs size N * ratio. Read straight from the OS/2 and head tables (no fontTools in a bare sandbox)."""
    import struct
    try:
        b = ff.read_bytes()
        n = struct.unpack(">H", b[4:6])[0]
        tables = {b[12 + 16 * i: 16 + 16 * i]: struct.unpack(">I", b[20 + 16 * i: 24 + 16 * i])[0] for i in range(n)}
        upem = struct.unpack(">H", b[tables[b"head"] + 18: tables[b"head"] + 20])[0]
        o = tables[b"OS/2"]
        win_a, win_d = struct.unpack(">HH", b[o + 74: o + 78])
        return (win_a + win_d) / upem if upem and win_a else 1.2
    except (OSError, KeyError, struct.error):
        return 1.2


def measurer(family: str, px: int):
    """(width_of(text) in px, ass_size): ASS sizes are line heights, so the size libass needs for an em of `px`."""
    from PIL import ImageFont
    ff = font_path(family)
    if not ff:
        f = ImageFont.load_default()
        return (lambda t: f.getlength(t) * px / 10), int(px * 1.2)
    f = ImageFont.truetype(str(ff), max(1, px))
    try:
        f.set_variation_by_axes([900])
    except Exception:
        pass
    return (lambda t: f.getlength(t)), int(round(px * win_ratio(ff)))


def fit_size(family: str, lines: list[str], max_w: float, max_px: int) -> int:
    width_of, _ = measurer(family, 100)
    widest = max((width_of(x) for x in lines), default=1) or 1
    return max(12, min(max_px, int(max_w * 100 / widest)))


# words that open a new clause: a good place to break BEFORE them
OPENERS = {"và", "nhưng", "mà", "thì", "vì", "nên", "để", "nếu", "khi", "rồi", "còn", "hay", "hoặc", "tại", "bởi",
           "and", "but", "so", "because", "if", "when", "then", "or"}


def _key(t: str) -> str:
    return t.lower().strip(".,:!?;…\"'()")


def break_score(w: dict, nxt: dict) -> float:
    """How good a caption break is between w and nxt (higher = a cleaner end of an idea)."""
    t, gap = w["text"], nxt["start"] - w["end"]
    sc = 0.0
    if t[-1:] in ".!?…":
        sc += 10
    elif t[-1:] in ",:;":
        sc += 6
    sc += 10 if gap > 0.6 else 5 if gap >= 0.3 else 2 if gap >= 0.18 else 0
    if nxt["text"][:1].isupper():   # whisper often drops the full stop but keeps the capital
        sc += 3
    if _key(nxt["text"]) in OPENERS:
        sc += 2
    if _key(t) in CONNECTORS:       # "uống trà với | đường" cuts an idea in half
        sc -= 6
    return sc


def _split(seg: list[dict], scores: list[float], gmin: int, gmax: int) -> list[list[dict]]:
    """Split one run (no hard break inside) into groups of <= gmax words, cutting where ideas end."""
    n = len(seg)
    if n <= gmax:
        return [seg]
    k = -(-n // gmax)
    target = n / k
    short = min(gmin, 2)
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - gmax), j):
            if best[i] == float("inf"):
                continue
            size = j - i
            cost = best[i] + 0.6 * abs(size - target) + (8 if size < short else 0)
            if j < n:
                cost -= scores[j - 1]   # break after word j-1
            if cost < best[j]:
                best[j], back[j] = cost, i
    out, j = [], n
    while j > 0:
        out.append(seg[back[j]:j])
        j = back[j]
    return out[::-1]


PHRASE_MAX = 8   # a phrase Claude wrote stays whole up to this many words (it wraps to two lines)


def phrase_breaks(words: list[dict], phrases: list[str]) -> set[int]:
    """Indices i (break after words[i]) where the phrases Claude wrote end, aligned on the spoken words, so the
    breaks survive edits to the cuts (words that were cut away are simply skipped)."""
    return _align(words, phrases)[0]


def _align(words: list[dict], phrases: list[str]) -> tuple[set[int], set[int]]:
    """(group ends, line breaks): word indices to break after. '|' inside a phrase = line break there."""
    from difflib import SequenceMatcher
    toks, ends, brs = [], set(), set()
    for ph in phrases:
        n0 = len(toks)
        for t in str(ph).replace("|", " | ").split():
            if t == "|":
                if len(toks) > n0:
                    brs.add(len(toks) - 1)
            elif _key(t):
                toks.append(_key(t))
        if len(toks) > n0:
            ends.add(len(toks) - 1)
    keys = [_key(w["text"]) for w in words]
    out, lb = set(), set()
    for blk in SequenceMatcher(None, toks, keys, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            if blk.a + k in ends:
                out.add(blk.b + k)
            if blk.a + k in brs:
                lb.add(blk.b + k)
    return out, lb


def line_break(texts: list[str], width_of, max_w: float, scores: list[float]) -> int | None:
    """Where to start the 2nd line of a caption that does not fit on one: the most even split, preferring good
    breaks and never after a word that leans on the next. Returns the index of the last word of line 1."""
    if len(texts) < 2:
        return None
    sp = width_of(" ")
    ws = [width_of(t) for t in texts]
    total = sum(ws) + sp * (len(ws) - 1)
    if total <= max_w:
        return None
    best, best_cost, left = None, float("inf"), 0.0
    for i in range(len(texts) - 1):
        left += ws[i] + (sp if i else 0)
        right = total - left - sp
        cost = abs(left - right) / max(total, 1) * 10 - 0.5 * (scores[i] if i < len(scores) else 0)
        if _key(texts[i]) in CONNECTORS:
            cost += 6
        if max(left, right) > max_w:
            cost += 20
        if cost < best_cost:
            best, best_cost = i, cost
    return best


def caption_groups(words: list[dict], gmin: int, gmax: int, end: float, keywords: set[str],
                   phrases: list[str] | None = None) -> list[dict]:
    """Caption groups that are complete ideas. With `phrases` (style.caption.phrases, written by Claude from the
    transcript), break exactly where they end. Otherwise (and inside anything left too long): always break at
    sentence ends and long pauses, then pick the breaks with the best score (punctuation, pauses, a new clause),
    never right after a word that leans on the next one."""
    groups: list[list[dict]] = []
    if words:
        scores = [break_score(w, nx) for w, nx in zip(words, words[1:])]
        cuts, brs = _align(words, phrases) if phrases else (set(), set())
        hard = 10 if not cuts else 100     # Claude's phrases decide; only a real silence still breaks them
        cap = max(gmax, PHRASE_MAX) if cuts else gmax
        start = 0
        for i in range(len(words)):
            last = i + 1 == len(words)
            silence = not last and words[i + 1]["start"] - words[i]["end"] > 1.0
            if last or i in cuts or silence or scores[i] >= hard:
                groups += _split(words[start:i + 1], scores[start:i], gmin, cap if cuts else gmax)
                start = i + 1
    else:
        scores, brs = [], set()
    index = {id(w): i for i, w in enumerate(words)}
    out = []
    for gi, g in enumerate(groups):
        st = max(0.0, g[0]["start"] - 0.05)
        nx = groups[gi + 1][0]["start"] - 0.05 if gi + 1 < len(groups) else end
        en = min(nx, g[-1]["end"] + 0.45, end)
        out.append({"id": f"cg{gi}", "start": round(st, 3), "end": round(max(en, st + 0.2), 3),
                    "words": [{"text": w["text"].rstrip(".,:;"), "start": w["start"], "end": w["end"],
                               "key": _key(w["text"]) in keywords, "br": index[id(w)] in brs and w is not g[-1]}
                              for w in g],
                    "scores": [scores[index[id(w)]] for w in g[:-1]]})
    return out


def set_line_breaks(groups: list[dict], family: str, px: int, max_w: float) -> None:
    """Groups too wide for one line get one explicit line break (unless Claude placed one with '|')."""
    width_of, _ = measurer(family, px)
    for g in groups:
        ws = g["words"]
        if any(w.get("br") for w in ws):
            continue
        k = line_break([w["text"] for w in ws], width_of, max_w, g.get("scores") or [])
        if k is not None:
            ws[k]["br"] = True


def build(sb: dict, words: list[dict], cut_path: Path, duration: float, project_dir: Path, ws: Path | None,
          tier: str = "pro", person: str | None = None) -> dict:
    o, st = sb["output"], sb.get("style", {})
    W, H = o["width"], o["height"]
    pal = {"ink": "#1F2A44", "accent": "#FFD84D", "text": "#FFFFFF", "spoken": "#9EE6FF", **st.get("palette", {})}
    font = {"title": "Montserrat", "caption": "Montserrat", **st.get("font", {})}
    plan: dict = {"W": W, "H": H, "fps": o["fps"], "duration": round(duration, 3), "video": str(cut_path),
                  "palette": pal, "font": font, "captions": None, "stamps": [], "cards": [], "walls": [], "hooks": [], "frames": [],
                  "transitions": [], "sfx": [], "bgm": None, "person": None, "background": None, "warnings": []}

    if person:
        from nve import background
        bg = st.get("background") or dict(background.DEFAULT)
        layers = background.layers(bg, duration)
        for ly in layers:
            if ly["kind"] == "image":
                ly["path"] = str(assets.resolve(ly["asset"], project_dir, ws, tier))
        ps = {"scale": 0.9, "y": 0.0, **(st.get("person") or {})}
        plan["person"] = {"path": person, "scale": ps["scale"], "y": int(H * ps["y"])}
        plan["background"] = {"layers": layers, "dots": bool(bg.get("dots", bg.get("type") != "image"))}

    cap = st.get("caption") or {}
    if cap.get("block") and cap.get("block") != "none" and words:
        blk = _block(cap["block"], ws)
        p = _props(blk, {k: v for k, v in cap.items() if k != "block"})
        kw = {k.lower() for k in p.get("keywords") or []}
        groups = caption_groups(words, p["group_min"], p["group_max"], duration, kw, cap.get("phrases"))
        if p.get("uppercase"):
            for g in groups:
                for w in g["words"]:
                    w["text"] = w["text"].upper()
        variant = blk.get("variant", "pill")
        side = (70 if variant == "pill" else 86) * W / 1080
        pad = 28 * W / 1080 if variant == "pill" else 0
        set_line_breaks(groups, font["caption"], int(W * p["size"]), (W - 2 * side - 2 * pad) * 0.97)
        plan["captions"] = {"block": blk["id"], "variant": variant, "top": int(H * p["top"]),
                            "size": int(W * p["size"]), "groups": groups}

    sfx_n = 0
    banned = set(st.get("ban_sfx") or [])  # the user's taste: never these sounds

    def add_sfx(ref: str, at: float, vol: float, mx: float | None = None) -> None:
        nonlocal sfx_n
        if at >= duration:
            return
        if ref.rsplit("/", 1)[-1].rsplit(".", 1)[0] in banned:
            return
        try:
            path = assets.resolve(ref, project_dir, ws, tier)
        except NveError as e:
            plan["warnings"].append(str(e))
            return
        plan["sfx"].append({"id": f"sfx{sfx_n}", "path": str(path), "at": round(max(0.0, at), 3), "volume": vol, "max": mx})
        sfx_n += 1

    for i, ov in enumerate(sorted(sb["tracks"].get("overlay", []), key=lambda x: x["start"])):
        blk = _block(ov["block"], ws)
        p = _props(blk, ov.get("props", {}))
        s, e = float(ov["start"]), min(float(ov["end"]), duration)
        if e - s < blk.get("min_duration", 0):
            plan["warnings"].append(f"{ov['block']} at {s}s is shorter than {blk['min_duration']}s")
        item = {"i": i, "block": blk["id"], "start": s, "end": e, "props": p, "top": int(H * p.get("top", 0.05))}
        if blk["id"].endswith("stamp.slam"):
            em = p.get("emoji") or []
            em = [em] if isinstance(em, str) else em
            item["emoji"] = []
            for cp in em:
                try:
                    item["emoji"].append({"cp": cp, "path": str(assets.emoji(cp, ws))})
                except NveError as err:
                    plan["warnings"].append(str(err))
            plan["stamps"].append(item)
        elif blk["id"].endswith("card.image"):
            item["img"] = str(assets.resolve(p["img"], project_dir, ws, tier))
            plan["cards"].append(item)
        elif blk["id"].endswith("hook.title"):
            item["marker"] = p.get("marker") or pal["accent"]
            item["size"] = fit_size(font["title"], plain(p["text"]).split("|"), W * 0.88, int(W * float(p.get("size") or 0.095)))
            plan["hooks"].append(item)
        elif blk["id"].endswith("media.frame"):
            item["src"] = str(assets.resolve(p["src"], project_dir, ws, tier))
            item["is_video"] = Path(item["src"]).suffix.lower() in (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
            fw = int(W * min(1.0, max(0.2, float(p.get("width") or 0.8)))) // 2 * 2
            try:
                aw, ah = (float(x) for x in str(p.get("aspect") or "4:3").split(":"))
            except ValueError:
                aw, ah = 4.0, 3.0
            item.update({"w": fw, "h": int(fw * ah / aw) // 2 * 2, "radius": int(W * float(p.get("radius") or 0.045)),
                         "in": float(p.get("in") or 0)})
            plan["frames"].append(item)
        elif blk["id"].endswith("media.wall"):
            item["img"] = str(assets.resolve(p["img"], project_dir, ws, tier))
            fx, fy = (list(p.get("focus") or [0.5, 0.5]) + [0.5, 0.5])[:2]
            z0, z1 = (list(p.get("zoom") or [1.0, 1.35]) + [1.0, 1.35])[:2]
            item.update({"focus": [min(1.0, max(0.0, float(fx))), min(1.0, max(0.0, float(fy)))],
                         "zoom": [max(1.0, float(z0)), max(1.0, float(z1))]})
            plan["walls"].append(item)
        else:
            plan["warnings"].append(f"block {blk['id']} has no renderer yet; skipped")
            continue
        for d in blk.get("default_sfx", []):
            if d.get("if") == "emoji" and not item.get("emoji"):
                continue
            add_sfx(d["asset"], s + d.get("at", 0), d.get("volume", 0.4), d.get("max"))
        for x in ov.get("sfx", []):  # extra per-overlay sfx: {"asset", "at" (relative), "volume"} or [name, at, vol]
            if isinstance(x, list):
                x = {"asset": f"lib:sfx/{x[0]}", "at": x[1], "volume": x[2] if len(x) > 2 else 0.4}
            add_sfx(x["asset"], s + x.get("at", 0), x.get("volume", 0.4), x.get("max"))

    # walls that follow each other (gap < 0.15 s) are joined with a hard cut: no fade, no flash of the video between
    walls = sorted(plan["walls"], key=lambda w: w["start"])
    for a, b in zip(walls, walls[1:]):
        if 0 <= b["start"] - a["end"] < 0.15:
            a["end"] = b["start"]
            a["cut_out"] = b["cut_in"] = True

    from nve import timeline, transitions
    segs = timeline.segments(sb["tracks"]["video"], o.get("speed", 1.0), o["fps"]) if sb["tracks"].get("video") else []
    trs, tw = transitions.resolve(sb, segs)
    plan["warnings"] += tw
    for t in trs:
        if t["at"] >= duration:
            continue
        if t["family"] == "cut":
            plan["transitions"].append({"at": t["at"], "type": t["type"], "duration": t["duration"]})
        for d in t["sfx"]:
            add_sfx(d["asset"], t["at"] + d.get("at", 0), d.get("volume", 0.3), d.get("max"))

    for a in sb["tracks"].get("audio", []):
        if a["kind"] == "bgm":
            try:
                plan["bgm"] = {"path": str(assets.resolve(a["asset"], project_dir, ws, tier)), "volume": a.get("volume", 0.1)}
            except NveError as e:
                plan["warnings"].append(f"bgm skipped: {e}")
        elif a["kind"] == "sfx":
            add_sfx(a["asset"], a.get("at", 0), a.get("volume", 0.4), a.get("max"))
    plan["credits"] = credits(plan)
    for w in plan["warnings"]:
        log(f"warning: {w}")
    return plan


def credits(plan: dict) -> list[str]:
    """Attribution lines required by the licences of what this render uses."""
    import json as _json
    from nve.paths import INSTALL_ROOT
    out = []
    if plan.get("bgm"):
        p = Path(plan["bgm"]["path"])
        man = INSTALL_ROOT / "packs" / "bgm" / "bgm.json"
        meta = p.parent / "meta.json"
        if p.parent == INSTALL_ROOT / "packs" / "bgm" and man.exists():
            m = _json.loads(man.read_text())
            t = m["tracks"].get(p.stem)
            if t:
                out.append(m["credit_template"].format(title=t["title"]))
        elif meta.exists():
            c = _json.loads(meta.read_text()).get("credit")
            if c:
                out.append(c)
    if any(s.get("emoji") for s in plan.get("stamps", [])):
        out.append("Emoji: Google Noto (CC BY 4.0)")
    return out
