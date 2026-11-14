"""Taste log: the user's corrections, kept as rules that shape the next videos.

Every time the user corrects an edit decision ("too many stamps", "that sound is cheesy"), Claude fixes the
video AND records the correction here in the user's own words, optionally with a machine part:

- set:   defaults for `output.*` / `style.*` (filled in at `nve plan draft`, below the storyboard),
- limit: a max/min on a metric measured from the storyboard (checked at `nve plan refresh` and preview),
- ban:   SFX or music the user never wants (written into `style.ban_sfx` / checked on bgm).

Rules live in `<workspace>/taste.json`. Taste is a prior: the storyboard always wins. Rules from the user
(`from: user`) are quoted back as "you said"; rules Claude learned itself are `from: skill`.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nve.paths import NveError
from nve.util import dump_json

SCHEMA = "nve.taste/1"
SETTABLE = ("output.", "style.")
METRICS = {
    "duration": "output length in seconds",
    "speed": "output.speed",
    "stamps_per_min": "highlight stamps per minute",
    "cards_per_min": "image cards per minute",
    "overlays_per_min": "all overlays per minute",
    "emoji_per_min": "emoji on stamps per minute",
    "sfx_per_min": "sound effects per minute (block defaults + extra + audio track)",
    "bgm_volume": "music volume (0-1)",
    "caption_words_max": "most words in one caption group",
}


def path(ws: Path) -> Path:
    return ws / "taste.json"


def load(ws: Path) -> dict:
    p = path(ws)
    if not p.exists():
        return {"schema": SCHEMA, "rules": []}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("rules", [])
    return data


def save(ws: Path, data: dict) -> None:
    dump_json(path(ws), data)


def _value(s: str):
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return s


def _next_id(rules: list[dict]) -> str:
    n = max((int(r["id"][1:]) for r in rules if r.get("id", "")[1:].isdigit()), default=0)
    return f"t{n + 1}"


def add(ws: Path, said: str, *, sets: list[str] | None = None, maxes: list[str] | None = None,
        mins: list[str] | None = None, ban_sfx: list[str] | None = None, ban_bgm: list[str] | None = None,
        template: str | None = None, source: str = "user", project: str | None = None) -> dict:
    if not said.strip():
        raise NveError("Write what the user said (their own words).")
    if source not in ("user", "skill"):
        raise NveError("--from must be user or skill")
    rule: dict = {"said": said.strip(), "from": source}
    for kv in sets or []:
        k, sep, v = kv.partition("=")
        if not sep or not k.startswith(SETTABLE):
            raise NveError(f"--set needs output.<key>=<value> or style.<key>=<value>, got '{kv}'")
        rule.setdefault("set", {})[k] = _value(v)
    for kind, items in (("max", maxes), ("min", mins)):
        for kv in items or []:
            k, sep, v = kv.partition("=")
            if not sep or k not in METRICS:
                raise NveError(f"--{kind} needs <metric>=<number>; metrics: {', '.join(METRICS)}")
            try:
                rule.setdefault("limit", {}).setdefault(k, {})[kind] = float(v)
            except ValueError:
                raise NveError(f"--{kind} {kv}: not a number") from None
    if ban_sfx:
        rule["ban_sfx"] = sorted(set(ban_sfx))
    if ban_bgm:
        rule["ban_bgm"] = sorted(set(ban_bgm))
    if template:
        rule["template"] = template
    if project:
        rule["project"] = project
    data = load(ws)
    rule = {"id": _next_id(data["rules"]), **rule, "added": date.today().isoformat(), "active": True}
    data["rules"].append(rule)
    save(ws, data)
    return rule


def set_active(ws: Path, rule_id: str, active: bool) -> dict:
    data = load(ws)
    for r in data["rules"]:
        if r["id"] == rule_id:
            r["active"] = active
            save(ws, data)
            return r
    raise NveError(f"No taste rule '{rule_id}'. See `nve taste list --all`.")


def rules_for(data: dict, template: str | None = None, chain: list[str] | None = None) -> list[dict]:
    """Active rules that apply to this template (rules without a template apply everywhere)."""
    ids = set(chain or []) | ({template} if template else set())
    return [r for r in data["rules"] if r.get("active", True) and (not r.get("template") or r["template"] in ids)]


def describe(r: dict) -> str:
    who = "you said" if r.get("from") == "user" else "skill rule"
    parts = [f'{r["id"]} ({who}): "{r["said"]}"']
    if r.get("set"):
        parts.append("set " + ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in r["set"].items()))
    for m, lim in (r.get("limit") or {}).items():
        parts.append(" ".join(f"{m} {'<=' if k == 'max' else '>='} {v:g}" for k, v in lim.items()))
    if r.get("ban_sfx"):
        parts.append("no SFX " + ", ".join(r["ban_sfx"]))
    if r.get("ban_bgm"):
        parts.append("no music " + ", ".join(r["ban_bgm"]))
    if r.get("template"):
        parts.append(f"only {r['template']}")
    return "; ".join(parts)


def prompt(ws: Path, template: str | None = None, chain: list[str] | None = None) -> dict:
    rules = rules_for(load(ws), template, chain)
    return {"rules": len(rules), "lines": [describe(r) for r in rules],
            "note": "Plan with these. They are defaults: the storyboard wins, but explain any rule you break."}


# ── applying ──
def _set_path(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def apply_defaults(sb: dict, rules: list[dict]) -> list[str]:
    """Fill a fresh draft storyboard with the taste's `set` values and SFX bans. Returns what changed."""
    changed = []
    for r in rules:
        for k, v in (r.get("set") or {}).items():
            _set_path(sb, k, v)
            changed.append(f"{k}={json.dumps(v, ensure_ascii=False)} ({r['id']})")
        if r.get("ban_sfx"):
            st = sb.setdefault("style", {})
            st["ban_sfx"] = sorted(set(st.get("ban_sfx", [])) | set(r["ban_sfx"]))
            changed.append(f"style.ban_sfx += {', '.join(r['ban_sfx'])} ({r['id']})")
    return changed


def _asset_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def metrics(sb: dict, duration: float, ws: Path | None = None) -> dict:
    from nve import registry
    mins = max(duration, 1.0) / 60
    ovs = sb["tracks"].get("overlay", [])
    stamps = [o for o in ovs if o["block"].endswith("stamp.slam")]
    cards = [o for o in ovs if o["block"].endswith("card.image")]
    sfx = 0
    for o in ovs:
        try:
            blk = registry.resolve(o["block"], "block", ws)
        except NveError:
            blk = {}
        has_emoji = bool((o.get("props") or {}).get("emoji"))
        sfx += sum(1 for d in blk.get("default_sfx", []) if d.get("if") != "emoji" or has_emoji)
        sfx += len(o.get("sfx", []))
    sfx += sum(1 for a in sb["tracks"].get("audio", []) if a["kind"] == "sfx")
    emoji = 0
    for o in stamps:
        e = (o.get("props") or {}).get("emoji") or []
        emoji += 1 if isinstance(e, str) else len(e)
    bgm = next((a for a in sb["tracks"].get("audio", []) if a["kind"] == "bgm"), None)
    cap = (sb.get("style") or {}).get("caption") or {}
    return {"duration": round(duration, 2), "speed": sb["output"].get("speed", 1.0),
            "stamps_per_min": round(len(stamps) / mins, 2), "cards_per_min": round(len(cards) / mins, 2),
            "overlays_per_min": round(len(ovs) / mins, 2), "emoji_per_min": round(emoji / mins, 2),
            "sfx_per_min": round(sfx / mins, 2), "bgm_volume": bgm.get("volume", 0.1) if bgm else None,
            "caption_words_max": cap.get("group_max") if cap.get("block") not in (None, "none") else None}


def check(sb: dict, duration: float, ws: Path, chain: list[str] | None = None) -> list[str]:
    """Warnings for every active rule the storyboard breaks, quoting the user's words."""
    rules = rules_for(load(ws), sb.get("template"), chain)
    if not rules:
        return []
    m = metrics(sb, duration, ws)
    used_sfx = {_asset_name(x[0] if isinstance(x, list) else x.get("asset", ""))
                for o in sb["tracks"].get("overlay", []) for x in o.get("sfx", [])}
    used_sfx |= {_asset_name(a["asset"]) for a in sb["tracks"].get("audio", []) if a["kind"] == "sfx"}
    used_bgm = {_asset_name(a["asset"]) for a in sb["tracks"].get("audio", []) if a["kind"] == "bgm"}
    banned_in_style = set((sb.get("style") or {}).get("ban_sfx", []))
    out = []
    for r in rules:
        quote = f'{r["id"]} "{r["said"]}"'
        for name, lim in (r.get("limit") or {}).items():
            v = m.get(name)
            if v is None:
                continue
            if "max" in lim and v > lim["max"]:
                out.append(f"taste {quote}: {name} is {v:g}, rule says at most {lim['max']:g}")
            if "min" in lim and v < lim["min"]:
                out.append(f"taste {quote}: {name} is {v:g}, rule says at least {lim['min']:g}")
        for k, want in (r.get("set") or {}).items():
            cur: object = sb
            for part in k.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            if cur != want:
                out.append(f"taste {quote}: {k} is {json.dumps(cur, ensure_ascii=False)}, "
                           f"rule says {json.dumps(want, ensure_ascii=False)}")
        for s in r.get("ban_sfx", []):
            if s in used_sfx:
                out.append(f"taste {quote}: SFX '{s}' is used")
            elif s not in banned_in_style:
                out.append(f"taste {quote}: add '{s}' to style.ban_sfx so block sounds skip it")
        for b in r.get("ban_bgm", []):
            if b in used_bgm:
                out.append(f"taste {quote}: music '{b}' is used")
    return out


# ── moving taste between sandboxes (claude.ai threads start empty) ──
def export(ws: Path) -> dict:
    data = load(ws)
    return {"schema": SCHEMA, "rules": [{k: v for k, v in r.items() if k not in ("id", "project")}
                                        for r in data["rules"] if r.get("active", True)]}


def import_(ws: Path, incoming: dict) -> dict:
    if incoming.get("schema") != SCHEMA:
        raise NveError(f"Not a taste export (schema must be {SCHEMA}).")
    data = load(ws)
    seen = {(r["said"], r.get("template"), json.dumps(r.get("set"), sort_keys=True)) for r in data["rules"]}
    added = []
    for r in incoming.get("rules", []):
        key = (r.get("said", ""), r.get("template"), json.dumps(r.get("set"), sort_keys=True))
        if not r.get("said") or key in seen:
            continue
        r = {"id": _next_id(data["rules"]), **{k: v for k, v in r.items() if k != "id"}, "active": True}
        data["rules"].append(r)
        seen.add(key)
        added.append(r["id"])
    save(ws, data)
    return {"added": added, "total": len(data["rules"])}
