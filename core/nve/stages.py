"""Pipeline stages S1-S9. Each stage reads/writes files in the project folder, so any stage can be
re-run on its own and the skill can resume a project in a new session."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import shutil
from pathlib import Path

from nve import compose_plan, registry, storyboard as SB, taste, timeline
from nve.engines import Ctx, run_capability
from nve.paths import NveError
from nve.project import Project
from nve.util import dump_json, duration, log, media_info, run

LABELS_VI = {"cut_strategy": {"speech": "theo lời nói", "visual": "theo hình", "beat": "theo nhịp nhạc", "hybrid": "kết hợp"}}


# ───────────────────────── S1 ingest ─────────────────────────
def ingest(prj: Project, ctx: Ctx, language: str | None = None, transcribe: str = "auto") -> dict:
    meta = prj.meta
    out = {"sources": [], "language": language}
    for s in meta["sources"]:
        path = prj.p(s["path"])
        info = media_info(path)
        info["id"] = s["id"]
        info["rel"] = s["path"]
        tpath = prj.p("analysis", "transcripts", f"{s['id']}.json")
        if info["kind"] == "video" and info["has_audio"] and transcribe != "no":
            if tpath.exists():
                info["transcript"] = f"analysis/transcripts/{s['id']}.json"
            else:
                try:
                    res = run_capability("transcribe", {"src": str(path), "out": str(tpath), "work": str(prj.p("work")),
                                                        "language": language}, ctx)
                    info["transcript"] = f"analysis/transcripts/{s['id']}.json"
                    info["transcript_engine"] = res["engine"]
                except NveError as e:
                    info["transcript_error"] = str(e)
                    log(f"no transcript for {s['id']}: {e}")
        if info.get("transcript"):
            eng = _transcript_engine(prj.p(info["transcript"]))
            info.setdefault("transcript_engine", eng)
            info["needs_review"] = eng != "scribe"
            sp = timeline.silences_path(prj.p(info["transcript"]))
            if eng != "scribe" and not sp.exists():
                dump_json(sp, [[round(a, 3), round(b, 3)] for a, b in silences(path)])
        if info["kind"] in ("video", "image"):
            info["greenscreen"] = detect_greenscreen(path, info)
        if info["kind"] == "video" and info["has_audio"]:
            info["loudness_lufs"] = loudness(path)
        words = timeline.load_words(prj.p(info["transcript"])) if info.get("transcript") else []
        if info["kind"] == "video" and info["has_audio"] and not info.get("transcript"):
            # no transcript engine worked: estimate speech from the audio and keep its pauses for cutting
            sp = prj.p("analysis", "transcripts", f"{s['id']}.silences.json")
            holes = silences(path)
            dump_json(sp, [[round(a, 3), round(b, 3)] for a, b in holes])
            voiced = info["duration"] - sum(b - a for a, b in holes)
            info["speech_ratio"] = round(voiced / info["duration"], 2) if info["duration"] else 0.0
            info["speech_estimated_from"] = "audio (no transcript: no captions, cuts on pauses only)"
            info["words"] = 0
            out["sources"].append(info)
            continue
        # speaking time = runs of words with short gaps, so natural pauses between words count as speech
        talk = sum(b - a for a, b in timeline.speech_ranges(words, info["duration"], 0.6, 0, 0, drop_fillers=False))
        info["words"] = len(words)
        info["speech_ratio"] = round(talk / info["duration"], 2) if info["duration"] else 0.0
        out["sources"].append(info)
    vids = [x for x in out["sources"] if x["kind"] == "video"]
    tot = sum(x["duration"] for x in vids) or 1
    ratio = sum(x["speech_ratio"] * x["duration"] for x in vids) / tot
    images = sum(1 for x in out["sources"] if x["kind"] == "image")
    out["speech_ratio"] = round(ratio, 2)
    out["suggested_strategy"] = "speech" if ratio >= 0.6 else ("hybrid" if ratio >= 0.25 else "visual")
    if images and not vids:
        out["suggested_strategy"] = "visual"
    quiet = [x for x in out["sources"] if x["kind"] == "video" and x.get("has_audio") and x.get("speech_ratio", 0) < 0.3]
    if quiet:
        out["ask_mute_audio"] = [{"source": x["id"], "loudness_lufs": x.get("loudness_lufs"),
                                  "noisy": (x.get("loudness_lufs") or -99) > -30} for x in quiet]
        out["hint_mute_audio"] = ("These clips have no speech. Ask the user whether to drop their own sound "
                                  "(sources[].audio = \"mute\") and let the music carry the video.")
    gs = [x["id"] for x in out["sources"] if (x.get("greenscreen") or {}).get("likely")]
    if gs:
        out["greenscreen_sources"] = gs
        out["hint_greenscreen"] = ("Green screen detected: plan draft turns on style.key and a default background. "
                                   "Look at a frame: if text on products reads backwards (front camera), set output.flip.")
    if any(x.get("needs_review") for x in out["sources"]):
        out["next"] = ("Transcript came from whisper: proof-read it before planning "
                       "(`nve transcript show`, write the corrections file, `nve transcript check`).")
    out["suggested_template"] = {"speech": "core:talking-head", "hybrid": "core:talking-head", "visual": "core:product-ad"}[out["suggested_strategy"]]
    dump_json(prj.p("analysis", "ingest.json"), out)
    prj.log("ingest", [f"{x['id']}: {x['kind']} {x.get('width', '')}x{x.get('height', '')} {x['duration']}s"
                       f"{' HDR' if x.get('hdr') else ''}, speech {int(x['speech_ratio'] * 100)}%"
                       f"{', transcript ' + x.get('transcript_engine', 'cached') if x.get('transcript') else ''}"
                       for x in out["sources"]] + [f"suggested cut strategy: {out['suggested_strategy']}"])
    return out


def loudness(path: Path) -> float | None:
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"], check=False)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr or "")
    return float(m[-1]) if m else None


def detect_greenscreen(path: Path, info: dict) -> dict:
    """Share of strongly green pixels in the frame border (top band + sides) on 3 frames. A green
    screen fills the border; a green shirt or plant does not. Also samples the screen colour."""
    import numpy as np
    from PIL import Image
    tmp = path.parent.parent / "work" / "gs"
    tmp.mkdir(parents=True, exist_ok=True)
    times = [0.0] if info["kind"] == "image" else [info["duration"] * f for f in (0.2, 0.5, 0.8)]
    ratios, cols = [], []
    for k, t in enumerate(times):
        p = tmp / f"{path.stem}_{k}.png"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=270:-2", str(p)])
        a = np.asarray(Image.open(p).convert("RGB")).astype(np.int16)
        h, w = a.shape[:2]
        border = np.concatenate([a[: h // 6].reshape(-1, 3), a[:, : w // 8].reshape(-1, 3), a[:, -w // 8:].reshape(-1, 3)])
        r, g, b = border[:, 0], border[:, 1], border[:, 2]
        m = (g > r + 25) & (g > b + 25) & (g > 60)
        ratios.append(float(m.mean()))
        if m.any():
            cols.append(np.median(border[m], axis=0))
    ratio = round(sum(ratios) / len(ratios), 2)
    out = {"border_green": ratio, "likely": ratio >= 0.35}
    if cols and out["likely"]:
        c = np.median(np.array(cols), axis=0).astype(int)
        out["screen"] = "#{:02X}{:02X}{:02X}".format(*c)
    return out


def silences(path: Path, noise_db: float | None = None, min_d: float = 0.4) -> list[tuple[float, float]]:
    """Pauses measured on the audio. Without noise_db, pick the loudest threshold that still calls
    at most ~30 % of the clip silent (adapts to room noise)."""
    def detect(db: float) -> list[tuple[float, float]]:
        r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                 f"silencedetect=noise={db}dB:d={min_d}", "-f", "null", "-"], check=False)
        st = [max(0.0, float(x)) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr or "")]
        en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr or "")]
        return list(zip(st, en))
    if noise_db is not None:
        return detect(noise_db)
    total = duration(path) or 1
    best: list[tuple[float, float]] = []
    for db in (-45, -40, -36, -32, -28, -25):
        h = detect(db)
        if sum(e - s for s, e in h) / total > 0.30:
            break
        best = h
    return best


# ───────────────────────── transcript review (L0 / whisper) ─────────────────────────
def _transcript_engine(path: Path) -> str:
    try:
        return json.loads(path.read_text()).get("engine") or "scribe"
    except Exception:
        return "unknown"


def transcript_show(prj: Project, src: str | None = None) -> list[dict]:
    """Numbered words, one line per phrase, for Claude to proof-read."""
    res = []
    for s in prj.meta["sources"]:
        if src and s["id"] != src:
            continue
        t = prj.p("analysis", "transcripts", f"{s['id']}.json")
        if not t.exists():
            continue
        words = timeline.load_raw_words(t)
        cp = timeline.corrections_path(t)
        fixes = json.loads(cp.read_text()).get("fixes", []) if cp.exists() else []
        lines, cur = [], []
        for i, w in enumerate(words):
            cur.append(f"{i}:{timeline.clean_text(w['text'])}")
            gap = i + 1 < len(words) and words[i + 1]["start"] - w["end"] > 0.35
            if gap or w["text"].rstrip()[-1:] in ".?!" or len(cur) >= 14 or i + 1 == len(words):
                lines.append(f"[{words[i - len(cur) + 1]['start']:.1f}s] " + " ".join(cur))
                cur = []
        eng = _transcript_engine(t)
        res.append({"source": s["id"], "engine": eng, "needs_review": eng != "scribe",
                    "corrections_file": str(cp.relative_to(prj.path)), "existing_fixes": len(fixes), "lines": lines})
    return res


def transcript_check(prj: Project, ctx: Ctx) -> dict:
    out = {}
    for s in prj.meta["sources"]:
        t = prj.p("analysis", "transcripts", f"{s['id']}.json")
        cp = timeline.corrections_path(t)
        if not cp.exists():
            continue
        try:
            fixes = json.loads(cp.read_text()).get("fixes", [])
        except json.JSONDecodeError as e:
            raise NveError(f"{cp.name} is not valid JSON: {e}") from e
        words, problems = timeline.apply_corrections(timeline.load_raw_words(t), fixes)
        out[s["id"]] = {"fixes": len(fixes), "applied": len(fixes) - len(problems), "problems": problems}
    if prj.storyboard_path.exists():
        refresh(prj, ctx)
    prj.log("transcript review", [f"{k}: {v['applied']}/{v['fixes']} fixes applied" for k, v in out.items()])
    return out


# ───────────────────────── visual analysis (shots) ─────────────────────────
def _edge_score(img) -> float:
    from PIL import ImageFilter, ImageStat
    g = img.convert("L").resize((270, int(270 * img.height / img.width)))
    return round(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0], 1)


def _cut_points(path: Path, src: dict, threshold: float) -> tuple[list[float], list[str]]:
    """Shot boundaries of one video: nve.analyze.shots (jump cuts, flashes, fades), else ffmpeg's scene score."""
    from nve.analyze import shots as AS
    try:
        sh = AS.shots_of(str(path), src.get("fps") or 30.0)
        if sh:
            return [x["start"] for x in sh] + [src["duration"]], [x["transition_in"] for x in sh]
    except Exception as e:  # noqa: BLE001 - any decode problem: fall back to ffmpeg
        log(f"shot detector failed on {path.name} ({e}); using ffmpeg scene detection")
    r = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{threshold})',showinfo",
             "-an", "-f", "null", "-"], check=False)
    cuts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr or "")]
    return [0.0] + [c for c in cuts if 0.3 < c < src["duration"] - 0.3] + [src["duration"]], []


def analyze_shots(prj: Project, threshold: float = 0.3) -> dict:
    """Split every video source into shots and score them, then build a contact sheet Claude can
    look at to choose moments (visual cut strategy)."""
    from PIL import Image, ImageChops, ImageDraw, ImageStat
    ing = json.loads(prj.p("analysis", "ingest.json").read_text())
    tmp = prj.p("work", "shots")
    tmp.mkdir(parents=True, exist_ok=True)
    shots = []
    for s in ing["sources"]:
        if s["kind"] == "image":
            shots.append({"id": f"{s['id']}", "src": s["id"], "in": 0.0, "out": 3.0, "image": True})
            continue
        if s["kind"] != "video":
            continue
        bounds, kinds = _cut_points(prj.p(s["rel"]), s, threshold)
        for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
            if b - a >= 0.4:
                shots.append({"id": f"{s['id']}{k + 1}", "src": s["id"], "in": round(a, 2), "out": round(b, 2),
                              **({"cut_in": kinds[k]} if kinds and kinds[k] != "start" else {})})
    thumbs = []
    for sh in shots:
        src = next(x for x in ing["sources"] if x["id"] == sh["src"])
        times = [0.0] if sh.get("image") else [sh["in"] + (sh["out"] - sh["in"]) * f for f in (0.15, 0.5, 0.85)]
        imgs = []
        for j, t in enumerate(times):
            p = tmp / f"{sh['id']}_{j}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(prj.p(src["rel"])), "-frames:v", "1",
                 "-vf", "scale=360:-2", str(p)])
            imgs.append(Image.open(p).convert("RGB"))
        sharp = [_edge_score(im) for im in imgs]
        bright = [ImageStat.Stat(im.convert("L")).mean[0] for im in imgs]
        motion = (ImageStat.Stat(ImageChops.difference(imgs[0], imgs[-1]).convert("L")).mean[0] if len(imgs) > 1 else 0)
        sh.update({"sharpness": round(min(sharp), 1), "brightness": round(sum(bright) / len(bright)),
                   "motion": round(motion, 1), "t_frames": [round(t, 2) for t in times]})
        sh["flags"] = [f for f, c in (("blurry", min(sharp) < 60), ("dark", sh["brightness"] < 45),
                                      ("overexposed", sh["brightness"] > 215), ("static", motion < 2 and len(imgs) > 1)) if c]
        thumbs.append((sh, imgs))
    # contact sheet: one row per shot, 3 frames + label
    if thumbs:
        tw = 240
        th = max(int(tw * im.height / im.width) for _, ims in thumbs for im in ims)
        rows = []
        for sh, ims in thumbs:
            row = Image.new("RGB", (tw * 3 + 260, th + 8), (24, 24, 28))
            for j, im in enumerate(ims):
                row.paste(im.resize((tw, int(tw * im.height / im.width))), (j * tw, 4))
            d = ImageDraw.Draw(row)
            d.text((tw * 3 + 10, 10), f"{sh['id']}  {sh['in']:.1f}-{sh['out']:.1f}s", fill=(255, 230, 120))
            d.text((tw * 3 + 10, 30), f"sharp {sh['sharpness']}  light {sh['brightness']}", fill=(220, 220, 220))
            d.text((tw * 3 + 10, 50), f"motion {sh['motion']}", fill=(220, 220, 220))
            if sh["flags"]:
                d.text((tw * 3 + 10, 70), ", ".join(sh["flags"]), fill=(255, 120, 120))
            rows.append(row)
        per = 8
        sheets = []
        for k in range(0, len(rows), per):
            chunk = rows[k:k + per]
            sheet = Image.new("RGB", (chunk[0].width, sum(r.height for r in chunk)), (0, 0, 0))
            y = 0
            for r_ in chunk:
                sheet.paste(r_, (0, y))
                y += r_.height
            p = prj.p("analysis", f"shots_sheet_{k // per + 1}.jpg")
            sheet.save(p, quality=85)
            sheets.append(str(p.relative_to(prj.path)))
    else:
        sheets = []
    res = {"shots": shots, "sheets": sheets}
    dump_json(prj.p("analysis", "shots.json"), res)
    return res


# ───────────────────────── S3 plan ─────────────────────────
def plan_draft(prj: Project, ctx: Ctx, template_id: str | None = None, strategy: str | None = None,
               overwrite: bool = False) -> dict:
    if prj.storyboard_path.exists() and not overwrite:
        raise NveError("storyboard.json already exists. Edit it, or pass --overwrite to start a new draft.")
    ing_p = prj.p("analysis", "ingest.json")
    if not ing_p.exists():
        raise NveError("Run `nve ingest` first.")
    ing = json.loads(ing_p.read_text())
    strategy = strategy or ing["suggested_strategy"]
    template_id = template_id or ing["suggested_template"]
    tpl = registry.resolve(template_id, "template", ctx.workspace, ctx.env.get("edition"))
    d = tpl.get("defaults", {})
    o = {**d.get("output", {})}
    first_vid = next((x for x in ing["sources"] if x["kind"] == "video"), None)
    if first_vid and not o.get("fps"):
        o["fps"] = 30 if first_vid["fps"] > 26 else 25
    sources = [{"id": x["id"], "path": x["rel"], "kind": x["kind"], **({"transcript": x["transcript"]} if x.get("transcript") else {})}
               for x in ing["sources"] if x["kind"] in ("video", "image")]
    video = []
    if strategy in ("speech", "hybrid"):
        cfg = tpl.get("cut", {})
        for x in ing["sources"]:
            if x["kind"] == "video" and x.get("transcript"):
                rs = timeline.speech_ranges(timeline.load_words(prj.p(x["transcript"])), x["duration"],
                                            cfg.get("gap", 0.45), cfg.get("pad_in", 0.12), cfg.get("pad_out", 0.20))
                sp = timeline.silences_path(prj.p(x["transcript"]))
                if sp.exists():
                    # whisper stretches words over pauses: also cut the pauses measured on the audio
                    holes = [h for h in json.loads(sp.read_text()) if h[1] - h[0] >= cfg.get("gap", 0.45)]
                    rs = timeline.subtract(rs, holes)
                video += [{"src": x["id"], "in": a, "out": b} for a, b in rs]
            elif x["kind"] == "video" and prj.p("analysis", "transcripts", f"{x['id']}.silences.json").exists():
                holes = [h for h in json.loads(prj.p("analysis", "transcripts", f"{x['id']}.silences.json").read_text())
                         if h[1] - h[0] >= cfg.get("gap", 0.45)]
                rs = timeline.subtract([[0.0, x["duration"]]], holes)
                video += [{"src": x["id"], "in": a, "out": b, "note": "cut on pauses (no transcript)"} for a, b in rs]
            elif x["kind"] == "video":
                video.append({"src": x["id"], "in": 0.0, "out": x["duration"], "note": "no speech found: whole clip"})
            elif x["kind"] == "image":
                video.append({"src": x["id"], "in": 0.0, "out": 2.5, "note": "photo"})
    else:
        shots = analyze_shots(prj)["shots"]
        lo, hi = tpl.get("cut", {}).get("shot_min", 1.5), tpl.get("cut", {}).get("shot_max", 3.5)
        for sh in shots:
            if sh.get("flags") and set(sh["flags"]) & {"blurry", "dark", "overexposed"}:
                continue
            length = min(hi, max(lo, (sh["out"] - sh["in"]) * 0.6))
            mid = (sh["in"] + sh["out"]) / 2
            a = max(sh["in"], mid - length / 2)
            video.append({"src": sh["src"], "in": round(a, 2), "out": round(min(sh["out"], a + length), 2),
                          "note": f"shot {sh['id']} (draft pick, check the contact sheet)"})
    style = json.loads(json.dumps(d.get("style", {})))
    gsrc = [x for x in ing["sources"] if (x.get("greenscreen") or {}).get("likely")]
    if gsrc:
        from nve.background import DEFAULT as BG_DEFAULT
        style["key"] = {"enabled": True, "screen": gsrc[0]["greenscreen"].get("screen", "#1D754E")}
        style.setdefault("background", dict(BG_DEFAULT))
        style.setdefault("person", {"scale": 0.9, "y": 0.0})
        o.setdefault("flip", False)
    sb = {"schema": "nve.storyboard/1", "project": prj.meta.get("name", prj.path.name), "template": template_id,
          "cut_strategy": strategy, "brief": "", "output": o, "style": style, "sources": sources,
          "tracks": {"video": video, "overlay": [], "audio": list(d.get("audio", []))},
          "text_fixes": dict(tpl.get("text_fixes", {})), "engines": {}, "gates": {"plan": None, "preview": None, "final": None}}
    applied = []
    if ctx.workspace:
        applied = taste.apply_defaults(sb, taste.rules_for(taste.load(ctx.workspace), template_id, tpl.get("_chain")))
        if applied:
            ctx.notes.append("taste applied: " + "; ".join(applied))
    errs = SB.validate(sb)
    if errs:
        raise NveError("Draft storyboard is invalid:\n" + "\n".join(errs))
    dump_json(prj.storyboard_path, sb)
    refresh(prj, ctx)
    prj.log("plan draft", [f"template {template_id}, cut strategy {strategy}, {len(video)} ranges"]
            + ([f"taste: {'; '.join(applied)}"] if applied else []))
    return sb


def refresh(prj: Project, ctx: Ctx) -> dict:
    """Validate the storyboard, recompute output-timeline words, rewrite storyboard.md."""
    sb = prj.load_storyboard()
    errs = SB.validate(sb)
    if errs:
        raise NveError("storyboard.json is invalid:\n" + "\n".join(errs))
    words = SB.words_out(prj.path, sb)
    dump_json(prj.p("analysis", "words_out.json"), words)
    prj.p("storyboard.md").write_text(SB.to_markdown(prj.path, sb, LABELS_VI), encoding="utf-8")
    o = sb["output"]
    dur = timeline.total_duration(sb["tracks"]["video"], o.get("speed", 1.0), o["fps"])
    return {"duration": dur, "words": len(words), "overlays": len(sb["tracks"].get("overlay", [])),
            "taste_warnings": taste_warnings(sb, dur, ctx)}


def taste_warnings(sb: dict, duration: float, ctx: Ctx) -> list[str]:
    if not ctx.workspace:
        return []
    try:
        chain = registry.resolve(sb["template"], "template", ctx.workspace, ctx.env.get("edition")).get("_chain")
    except NveError:
        chain = None
    return taste.check(sb, duration, ctx.workspace, chain)


# ───────────────────────── S5-S8 cut + compose ─────────────────────────
def _segments(prj: Project, sb: dict) -> list[dict]:
    o = sb["output"]
    infos = {s["id"]: s for s in json.loads(prj.p("analysis", "ingest.json").read_text())["sources"]}
    srcs = {s["id"]: s for s in sb["sources"]}
    segs = timeline.segments(sb["tracks"]["video"], o.get("speed", 1.0), o["fps"])
    for s in segs:
        info = infos.get(s["src"], {})
        muted = s.get("mute") or srcs[s["src"]].get("audio") == "mute"
        s.update({"path": str(prj.p(srcs[s["src"]]["path"])), "kind": info.get("kind", srcs[s["src"]].get("kind", "video")),
                  "hdr": info.get("hdr", False), "has_audio": info.get("has_audio", False) and not muted})
    return segs


def cut(prj: Project, ctx: Ctx, proxy: bool = False) -> dict:
    sb = prj.load_storyboard()
    o, st = sb["output"], sb.get("style", {})
    W, H = (o["width"] // 2 // 2 * 2, o["height"] // 2 // 2 * 2) if proxy else (o["width"], o["height"])
    name = "proxy" if proxy else "cut"
    job = {"segments": _segments(prj, sb), "width": W, "height": H, "fps": o["fps"], "look": st.get("look", "none"),
           "skin": bool(st.get("skin")), "proxy": proxy, "work": str(prj.p("work", f"segs_{name}")),
           "out": str(prj.p("work", f"{name}.mp4"))}
    job["flip"] = bool(o.get("flip"))
    res = run_capability("cut", job, ctx)
    words = SB.words_out(prj.path, sb)
    dump_json(prj.p("work", "words.json"), words)
    res["duration"] = duration(Path(res["out"]))
    key = st.get("key") or {}
    if key.get("enabled"):
        person = prj.p("work", f"person_{name}.webm")
        kres = run_capability("key", {"src": res["out"], "out": str(person), "width": W, "height": H, "fps": o["fps"],
                                      "screen": key.get("screen")}, ctx)
        res["person"], res["key_engine"] = str(person), kres["engine"]
    return res


def _render_plan(prj: Project, ctx: Ctx, cut_path: Path, scale: float = 1.0, person: str | None = None) -> dict:
    sb = prj.load_storyboard()
    sbx = json.loads(json.dumps(sb))
    if scale != 1.0:
        sbx["output"] = {**sb["output"], "width": int(sb["output"]["width"] * scale) // 2 * 2,
                         "height": int(sb["output"]["height"] * scale) // 2 * 2}
    words = json.loads(prj.p("work", "words.json").read_text())
    tier = ctx.env.get("edition", {}).get("tier", "standard")
    return compose_plan.build(sbx, words, cut_path, duration(cut_path), prj.path, ctx.workspace, tier, person)


def preview(prj: Project, ctx: Ctx, times: list[float] | None = None) -> dict:
    sb = prj.load_storyboard()
    if not (sb.get("gates") or {}).get("plan"):
        log("note: the plan gate is not approved yet; this preview is for discussion")
    c = cut(prj, ctx, proxy=True)
    plan = _render_plan(prj, ctx, Path(c["out"]), scale=0.5, person=c.get("person"))
    if not times:
        times = []
        for ov in sorted(sb["tracks"].get("overlay", []), key=lambda x: x["start"]):
            times.append(round(min(ov["end"] - 0.05, ov["start"] + 0.55), 2))
        caps = (plan.get("captions") or {}).get("groups", [])
        if caps:
            g = caps[len(caps) // 2]
            times.append(round((g["start"] + g["end"]) / 2, 2))
        if not times:
            times = [round(plan["duration"] * f, 2) for f in (0.1, 0.4, 0.7, 0.95)]
    times = sorted({t for t in times if 0 <= t < plan["duration"]})[:12]
    sd = prj.p("preview", "stills")
    if sd.exists():
        shutil.rmtree(sd)
    res = run_capability("compose", {"plan": plan, "work": str(prj.p("work", "preview")), "snapshot_at": times,
                                     "snapshot_dir": str(sd)}, ctx)
    stills, labels = [Path(p) for p in res["stills"]], list(times)
    if (sb.get("cover") or {}).get("text"):
        cj = make_cover(prj, ctx, plan, sb, prj.p("preview", "cover.jpg"), "work/preview_cover")
        if cj:
            stills, labels = [cj] + stills, ["cover"] + labels
    sheet = make_sheet(stills, labels, prj.p("preview", "sheet.jpg"))
    prj.log("preview", [f"engine {res['engine']}, {len(times)} stills at {', '.join(f'{t:.1f}s' for t in times)}"] + ctx.notes)
    return {"sheet": str(sheet), "stills": res["stills"], "times": times, "engine": res["engine"], "warnings": plan["warnings"],
            "taste_warnings": taste_warnings(sb, plan["duration"], ctx)}


def make_sheet(stills: list[Path], times: list[float], out: Path) -> Path:
    from PIL import Image, ImageDraw
    ims = [Image.open(p).convert("RGB") for p in stills]
    if not ims:
        raise NveError("No preview stills were produced.")
    tw = 360
    th = int(tw * ims[0].height / ims[0].width)
    cols = min(4, len(ims))
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 28)), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for k, (im, t) in enumerate(zip(ims, times)):
        x, y = (k % cols) * tw, (k // cols) * (th + 28)
        sheet.paste(im.resize((tw, th)), (x, y + 28))
        label = "ẢNH BÌA (cover)" if t == "cover" else f"{int(t // 60)}:{t % 60:05.2f}"
        d.text((x + 8, y + 7), f"{k + 1}. {label}", fill=(255, 220, 90))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


def _cover_plan(plan: dict, cover: dict, ws: Path | None) -> dict:
    """Same picture as the video at cover.at, without captions/cards/sound, plus the cover title."""
    import copy
    from nve import assets
    p = copy.deepcopy(plan)
    t = float(cover.get("at", 0.5))
    p.update({"captions": None, "cards": [], "walls": [], "sfx": [], "bgm": None, "warnings": []})
    emoji = []
    for cp in ([cover["emoji"]] if isinstance(cover.get("emoji"), str) else cover.get("emoji", [])):
        try:
            emoji.append({"cp": cp, "path": str(assets.emoji(cp, ws))})
        except NveError as e:
            p["warnings"].append(str(e))
    p["stamps"] = [{"i": 900, "block": "core:stamp.slam", "start": max(0.0, t - 0.6), "end": t + 0.6,
                    "props": {"text": cover["text"], "alt": cover.get("alt", True), "scale": cover.get("scale", 1.25)},
                    "top": int(p["H"] * cover.get("top", 0.12)), "emoji": emoji}]
    p["duration"] = round(min(plan["duration"], t + 0.7), 3)
    return p


def make_cover(prj: Project, ctx: Ctx, plan: dict, sb: dict, out_jpg: Path, work: str) -> Path | None:
    cover = sb.get("cover") or {}
    if not cover.get("text"):
        return None
    t = float(cover.get("at", 0.5))
    if t >= plan["duration"]:
        raise NveError(f"cover.at ({t}s) is after the end of the video ({plan['duration']}s)")
    cp = _cover_plan(plan, cover, ctx.workspace)
    sd = prj.p(work, "cover_still")
    if sd.exists():
        shutil.rmtree(sd)
    res = run_capability("compose", {"plan": cp, "work": str(prj.p(work)), "snapshot_at": [t], "snapshot_dir": str(sd)}, ctx)
    from PIL import Image
    Image.open(res["stills"][0]).convert("RGB").save(out_jpg, quality=93)
    return out_jpg


def prepend_cover(cover_jpg: Path, video: Path, out: Path, W: int, H: int, fps: int, seconds: float) -> None:
    """Put the cover as a still at the start (silent), so it is the first thing seen and the feed thumbnail."""
    fc = (f"[0:v]scale={W}:{H},fps={fps},format=yuv420p,setsar=1[c];[2:v]fps={fps},format=yuv420p,setsar=1[m];"
          f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[ca];[2:a]aformat=sample_rates=48000:channel_layouts=stereo[ma];"
          f"[c][ca][m][ma]concat=n=2:v=1:a=1[v][a]")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", f"{seconds:.3f}", "-i", str(cover_jpg),
         "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo", "-i", str(video),
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])


def render(prj: Project, ctx: Ctx, force: bool = False, phone: bool = False) -> dict:
    sb = prj.load_storyboard()
    gates = sb.get("gates") or {}
    if not force and not gates.get("plan"):
        raise NveError("The plan is not approved yet (gate G1). Approve with `nve approve plan`, or pass --force "
                       "if the user said to render right away.")
    if not force and not gates.get("preview"):
        raise NveError("The preview is not approved yet (gate G2). Run `nve preview`, then `nve approve preview`; "
                       "or pass --force if the user said to render right away.")
    c = cut(prj, ctx)
    plan = _render_plan(prj, ctx, Path(c["out"]), person=c.get("person"))
    name = prj.next_render_name()
    out = prj.p("renders", f"{name}.mp4")
    cover = sb.get("cover") or {}
    body = prj.p("work", f"{name}_body.mp4") if cover.get("prepend") and cover.get("text") else out
    res = run_capability("compose", {"plan": plan, "work": str(prj.p("work")), "out": str(body)}, ctx)
    result = {"final": str(out), "engine": res["engine"], "cut_engine": c["engine"], "key_engine": c.get("key_engine"),
              "warnings": plan["warnings"], "notes": list(ctx.notes)}
    cj = make_cover(prj, ctx, plan, sb, prj.p("renders", f"{name}_cover.jpg"), "work/cover")
    if cj:
        result["cover"] = str(cj)
        if body != out:
            o = sb["output"]
            prepend_cover(cj, body, out, o["width"], o["height"], o["fps"], float(cover.get("seconds", 1.0)))
            result["cover_prepended_s"] = float(cover.get("seconds", 1.0))
    if phone:
        ph = prj.p("renders", f"{name}_phone.mp4")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-c:v", "libx264", "-crf", "24", "-preset", "medium",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(ph)])
        result["phone"] = str(ph)
    result["qc"] = qc(prj, out, sb)
    if plan.get("credits"):
        cf = prj.p("renders", f"{name}.credits.txt")
        cf.write_text("\n".join(plan["credits"]) + "\n", encoding="utf-8")
        result["credits"] = plan["credits"]
        result["credits_note"] = "Paste these lines into the post description (license requirement)."
    prj.log(f"render {name}", [f"compose engine {res['engine']}, cut engine {c['engine']}",
                               f"cover: {'prepended ' if result.get('cover_prepended_s') else ''}{result.get('cover', 'none')}",
                               f"QC: {result['qc']['summary']}"] + plan["warnings"] + ctx.notes)
    return result


# ───────────────────────── S9 QC ─────────────────────────
def qc(prj: Project, video: Path, sb: dict | None = None) -> dict:
    info = media_info(video)
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], check=False)
    tail = (r.stderr or "")[-1500:]
    lufs = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    res = {"duration": info["duration"], "width": info.get("width"), "height": info.get("height"), "fps": info.get("fps"),
           "has_audio": info["has_audio"], "size_mb": round(video.stat().st_size / 1e6, 1),
           "lufs": float(lufs.group(1)) if lufs else None, "true_peak": float(peak.group(1)) if peak else None, "issues": []}
    if sb:
        o = sb["output"]
        if (res["width"], res["height"]) != (o["width"], o["height"]):
            res["issues"].append(f"size {res['width']}x{res['height']} != planned {o['width']}x{o['height']}")
    if not res["has_audio"]:
        res["issues"].append("no audio stream")
    if res["lufs"] is not None and not -16.5 <= res["lufs"] <= -12.5:
        res["issues"].append(f"loudness {res['lufs']} LUFS (target -14)")
    if res["true_peak"] is not None and res["true_peak"] > -1.0:
        res["issues"].append(f"true peak {res['true_peak']} dBTP (limit -1)")
    res["summary"] = (f"{res['duration']}s {res['width']}x{res['height']} {res['size_mb']} MB, "
                      f"{res['lufs']} LUFS, peak {res['true_peak']}") + (f", ISSUES: {'; '.join(res['issues'])}" if res["issues"] else ", OK")
    dump_json(prj.p("renders", f"{video.stem}.qc.json"), res)
    return res


def approve(prj: Project, gate: str, reopen: bool = False) -> dict:
    sb = prj.load_storyboard()
    SB.set_gate(sb, gate, None if reopen else dt.datetime.now().isoformat(timespec="minutes"))
    dump_json(prj.storyboard_path, sb)
    refresh(prj, Ctx(env={}, workspace=None))
    prj.log(f"gate {gate} {'reopened' if reopen else 'approved'}", [])
    return sb["gates"]
