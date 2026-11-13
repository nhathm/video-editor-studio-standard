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


def caption_groups(words: list[dict], gmin: int, gmax: int, end: float, keywords: set[str]) -> list[dict]:
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        last = i + 1 == len(words)
        punct = w["text"][-1:] in ".,:!?;"
        gap_next = not last and words[i + 1]["start"] - w["end"] > 0.6
        # whisper often omits the full stop but keeps the capital letter of the next sentence
        new_sentence = not last and words[i + 1]["text"][:1].isupper() and len(cur) >= 2
        if last or gap_next or new_sentence or len(cur) >= gmax or (punct and len(cur) >= min(gmin, 2)):
            groups.append(cur)
            cur = []
    out = []
    for gi, g in enumerate(groups):
        st = max(0.0, g[0]["start"] - 0.05)
        nx = groups[gi + 1][0]["start"] - 0.05 if gi + 1 < len(groups) else end
        en = min(nx, g[-1]["end"] + 0.45, end)
        out.append({"id": f"cg{gi}", "start": round(st, 3), "end": round(max(en, st + 0.2), 3),
                    "words": [{"text": w["text"].rstrip(".,:;"), "start": w["start"], "end": w["end"],
                               "key": w["text"].lower().strip(".,:!?;") in keywords} for w in g]})
    return out


def build(sb: dict, words: list[dict], cut_path: Path, duration: float, project_dir: Path, ws: Path | None,
          tier: str = "pro", person: str | None = None) -> dict:
    o, st = sb["output"], sb.get("style", {})
    W, H = o["width"], o["height"]
    pal = {"ink": "#1F2A44", "accent": "#FFD84D", "text": "#FFFFFF", "spoken": "#9EE6FF", **st.get("palette", {})}
    font = {"title": "Montserrat", "caption": "Montserrat", **st.get("font", {})}
    plan: dict = {"W": W, "H": H, "fps": o["fps"], "duration": round(duration, 3), "video": str(cut_path),
                  "palette": pal, "font": font, "captions": None, "stamps": [], "cards": [], "sfx": [], "bgm": None, "person": None, "background": None,
                  "warnings": []}

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
        plan["captions"] = {"block": blk["id"], "top": int(H * p["top"]), "size": int(W * p["size"]),
                            "groups": caption_groups(words, p["group_min"], p["group_max"], duration, kw)}

    sfx_n = 0

    def add_sfx(ref: str, at: float, vol: float, mx: float | None = None) -> None:
        nonlocal sfx_n
        if at >= duration:
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
