"""Storyboard: validate, fill defaults from the template, render the human-readable .md."""
from __future__ import annotations

import json
from pathlib import Path

from nve.paths import NveError
from nve.registry import deep_merge
from nve.timeline import load_words, output_words, segments, total_duration

SCHEMA_PATH = Path(__file__).parent / "schema" / "storyboard.schema.json"
GATES = ("plan", "preview", "final")


def validate(sb: dict) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema
        v = jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))
        errors += [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in v.iter_errors(sb)]
    except ImportError:
        for k in ("schema", "template", "cut_strategy", "output", "sources", "tracks"):
            if k not in sb:
                errors.append(f"(root): '{k}' is required")
    if errors:
        return errors
    src_ids = {s["id"] for s in sb["sources"]}
    for i, r in enumerate(sb["tracks"]["video"]):
        if r["src"] not in src_ids:
            errors.append(f"tracks/video/{i}: unknown source '{r['src']}'")
        if r["out"] <= r["in"]:
            errors.append(f"tracks/video/{i}: out ({r['out']}) must be after in ({r['in']})")
    o = sb["output"]
    dur = total_duration(sb["tracks"]["video"], o.get("speed", 1.0), o["fps"]) if sb["tracks"]["video"] else 0
    for i, ov in enumerate(sb["tracks"].get("overlay", [])):
        if ov["end"] <= ov["start"]:
            errors.append(f"tracks/overlay/{i}: end must be after start")
        if dur and ov["start"] >= dur:
            errors.append(f"tracks/overlay/{i}: starts at {ov['start']}s but the cut is only {dur}s long")
    return errors


def lint(sb: dict, duration: float) -> list[str]:
    """Editorial checks that are not errors: hook too long to read, text under the app's buttons, transitions
    that cannot be done as asked."""
    from nve import transitions
    out: list[str] = []
    o, st = sb["output"], sb.get("style", {})
    vertical = o["height"] > o["width"]
    cap = st.get("caption") or {}
    if vertical and cap.get("block") not in (None, "none") and float(cap.get("top", 0.68)) > 0.75:
        out.append(f"style.caption.top {cap['top']}: captions may sit under the app's buttons and description; keep top <= 0.75")
    for i, ov in enumerate(sb["tracks"].get("overlay", [])):
        text = str((ov.get("props") or {}).get("text", "")).replace("*", "")
        if ov["block"].endswith("hook.title"):
            n = len(text.replace("|", " ").split())
            d = ov["end"] - ov["start"]
            if n > 7:
                out.append(f"tracks/overlay/{i}: hook has {n} words; 2-6 words read in time")
            if d < 0.6 + n / 3.5:
                out.append(f"tracks/overlay/{i}: hook shows {d:.1f}s, needs about {0.6 + n / 3.5:.1f}s to read")
            if ov["start"] > 0.5:
                out.append(f"tracks/overlay/{i}: hook starts at {ov['start']}s; it should be on screen in the first half second")
        if text.count("|") >= 2 and ov["block"].endswith(("stamp.slam", "hook.title")):
            out.append(f"tracks/overlay/{i}: more than 2 lines of text")
    if sb["tracks"]["video"]:
        out += transitions.resolve(sb, segments(sb["tracks"]["video"], o.get("speed", 1.0), o["fps"]))[1]
    return out


def apply_template(sb: dict, template: dict) -> dict:
    """Template defaults fill whatever the storyboard leaves out; the storyboard always wins."""
    d = template.get("defaults", {})
    out = dict(sb)
    for key in ("output", "style"):
        out[key] = deep_merge(d.get(key, {}), sb.get(key, {}))
    out.setdefault("cut_strategy", template.get("cut_strategy", "speech"))
    return out


def transcripts_for(prj_path: Path, sb: dict) -> dict[str, list[dict]]:
    return {s["id"]: load_words(prj_path / s["transcript"]) if s.get("transcript") else [] for s in sb["sources"]}


def words_out(prj_path: Path, sb: dict) -> list[dict]:
    o = sb["output"]
    return output_words(sb["tracks"]["video"], transcripts_for(prj_path, sb), o.get("speed", 1.0), o["fps"],
                        sb.get("text_fixes"))


def _fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def _said(words: list[dict], a: float, b: float) -> str:
    return " ".join(w["text"] for w in words if w["start"] < b and w["end"] > a)


def to_markdown(prj_path: Path, sb: dict, labels: dict | None = None) -> str:
    L = labels or {}
    o, st = sb["output"], sb.get("style", {})
    speed, fps = o.get("speed", 1.0), o["fps"]
    segs = segments(sb["tracks"]["video"], speed, fps)
    words = words_out(prj_path, sb)
    total = sum(s["out_dur"] for s in segs)
    strat = L.get("cut_strategy", {}).get(sb["cut_strategy"], sb["cut_strategy"])
    font = st.get("font", {})
    lines = [
        f"# Storyboard: {sb.get('project', prj_path.name)}",
        "",
        f"- Template: `{sb['template']}` · cut: **{strat}** · output {o['width']}×{o['height']} @ {fps} fps"
        f" · speed {speed}× · length **{total:.1f}s**",
        f"- Look: {st.get('look', 'none')}{' + skin retouch' if st.get('skin') else ''} · fonts: "
        f"{font.get('title', '?')} / {font.get('caption', '?')}",
    ]
    if sb.get("brief"):
        lines.append(f"- Brief: {sb['brief']}")
    gates = sb.get("gates", {})
    lines.append("- Gates: " + " · ".join(f"{g} {'✓' if gates.get(g) else '…'}" for g in GATES))
    lines += ["", "## Cuts (what is kept)", "", "| # | out time | source | src in→out | said / note |", "|---|---|---|---|---|"]
    for i, s in enumerate(segs):
        said = _said(words, s["out_start"], s["out_start"] + s["out_dur"])
        note = s.get("note", "")
        lines.append(f"| {i + 1} | {_fmt(s['out_start'])}–{_fmt(s['out_start'] + s['out_dur'])} | {s['src']} | "
                     f"{s['in']:.2f}→{s['out']:.2f} | {(note + ' · ') if note else ''}{said[:90]} |")
    ovs = sorted(sb["tracks"].get("overlay", []), key=lambda x: x["start"])
    if ovs:
        lines += ["", "## On screen", "", "| time | block | content | while saying |", "|---|---|---|---|"]
        for ov in ovs:
            p = ov.get("props", {})
            content = p.get("text") or p.get("label") or p.get("img") or ""
            if p.get("emoji"):
                content += f" · emoji {','.join(p['emoji']) if isinstance(p['emoji'], list) else p['emoji']}"
            lines.append(f"| {_fmt(ov['start'])}–{_fmt(ov['end'])} | {ov['block']} | {str(content).replace('|', '/')} | "
                         f"{_said(words, ov['start'], ov['end'])[:60]} |")
    auds = sb["tracks"].get("audio", [])
    if auds:
        lines += ["", "## Sound", ""]
        for a in auds:
            when = f" at {_fmt(a['at'])}" if "at" in a else ""
            lines.append(f"- {a['kind']}: `{a['asset']}`{when} · vol {a.get('volume', 1)}")
    fixed = []
    for s in sb["sources"]:
        if s.get("transcript"):
            from nve.timeline import apply_corrections, corrections_path, load_raw_words
            cp = corrections_path(prj_path / s["transcript"])
            if cp.exists():
                ws, _ = apply_corrections(load_raw_words(prj_path / s["transcript"]), json.loads(cp.read_text()).get("fixes", []))
                fixed += [f"{w['corrected_from']} → {w['text']}" for w in ws if "corrected_from" in w]
    if fixed:
        lines += ["", f"## Transcript corrections ({len(fixed)})", "", ", ".join(fixed)]
    if sb.get("text_fixes"):
        lines += ["", "Brand fixes: " + ", ".join(f"{a} → {b}" for a, b in sb["text_fixes"].items())]
    cap = st.get("caption", {})
    if cap:
        lines += ["", f"Captions: `{cap.get('block', 'none')}`, keywords: {', '.join(cap.get('keywords', [])) or '—'}"]
    return "\n".join(lines) + "\n"


def set_gate(sb: dict, gate: str, value: str | None) -> dict:
    if gate not in GATES:
        raise NveError(f"Unknown gate '{gate}'. Gates: {', '.join(GATES)}")
    sb.setdefault("gates", {})[gate] = value
    if value is None:  # reopening a gate reopens everything after it
        for g in GATES[GATES.index(gate) + 1:]:
            sb["gates"][g] = None
    return sb
