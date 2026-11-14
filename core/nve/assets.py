"""Asset lookup. An asset ref is one of:
    lib:<type>/<name>     searched in: workspace custom/ -> workspace library/ -> pro/packs -> packs
    emoji:<codepoint>     Noto animated emoji (Lottie JSON)
    <relative path>       relative to the project folder
    <absolute path>
Missing Noto emoji are downloaded into the workspace library when the network allows.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from nve.paths import INSTALL_ROOT, PRO_ROOT, NveError
from nve.util import log

EXTS = {"sfx": (".mp3", ".wav", ".m4a"), "bgm": (".wav", ".mp3", ".m4a"), "img": (".png", ".jpg", ".jpeg", ".webp"),
        "font": (".ttf", ".otf", ".woff2"), "lottie": (".json",)}
PACK_DIRS = {"sfx": ["sfx", "sfx-extra"], "bgm": ["bgm"], "img": ["img"], "lottie": ["emoji-noto"]}
NOTO_URL = "https://fonts.gstatic.com/s/e/notoemoji/latest/{cp}/lottie.json"


def _search(dirs: list[Path], name: str, exts: tuple[str, ...]) -> Path | None:
    for d in dirs:
        for ext in ("",) + exts:
            p = d / f"{name}{ext}"
            if p.is_file():
                return p
            if p.is_dir():  # library/<type>/<name>/<file>
                files = [f for f in p.iterdir() if f.suffix.lower() in exts]
                if files:
                    return files[0]
    return None


def resolve(ref: str, project_dir: Path | None = None, workspace: Path | None = None, tier: str = "pro") -> Path:
    if ref.startswith("lib:"):
        typ, _, name = ref[4:].partition("/")
        dirs: list[Path] = []
        if workspace:
            dirs += [workspace / "custom" / typ, workspace / "library" / typ]
        packs = [PRO_ROOT / "packs" / d for d in PACK_DIRS.get(typ, [typ])] if tier == "pro" else []
        packs += [INSTALL_ROOT / "packs" / d for d in PACK_DIRS.get(typ, [typ])]
        p = _search(dirs + packs, name, EXTS.get(typ, ()))
        if p:
            return p
        raise NveError(f"Asset not found: {ref}")
    if ref.startswith("emoji:"):
        return emoji(ref[6:], workspace)
    p = Path(ref)
    if not p.is_absolute() and project_dir:
        p = project_dir / p
    if p.exists():
        return p
    raise NveError(f"Asset not found: {ref}")


def emoji(cp: str, workspace: Path | None) -> Path:
    cp = cp.lower().replace("u+", "")
    for d in ([workspace / "library" / "emoji-noto"] if workspace else []) + [INSTALL_ROOT / "packs" / "emoji-noto"]:
        if (d / f"{cp}.json").exists():
            return d / f"{cp}.json"
    if not workspace:
        raise NveError(f"Noto emoji {cp} not bundled and no workspace to download into.")
    dest = workspace / "library" / "emoji-noto" / f"{cp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(NOTO_URL.format(cp=cp), timeout=20) as r:
            dest.write_bytes(r.read())
        log(f"downloaded Noto emoji {cp} into the library (CC BY 4.0)")
        return dest
    except Exception as e:
        raise NveError(f"Noto emoji {cp} unavailable ({e}). It may have no animated version: pick another emoji.") from e


def list_assets(typ: str, workspace: Path | None, tier: str = "pro", detail: bool = False):
    if detail and typ == "bgm":
        return bgm_catalog(workspace, tier)
    names: set[str] = set()
    dirs = ([workspace / "custom" / typ, workspace / "library" / typ] if workspace else [])
    dirs += ([PRO_ROOT / "packs" / d for d in PACK_DIRS.get(typ, [typ])] if tier == "pro" else [])
    dirs += [INSTALL_ROOT / "packs" / d for d in PACK_DIRS.get(typ, [typ])]
    for d in dirs:
        if d.is_dir():
            for f in d.iterdir():
                if f.suffix.lower() in EXTS.get(typ, ()) or f.is_dir():
                    names.add(f.stem)
    return sorted(names)


def bgm_catalog(workspace: Path | None, tier: str = "pro") -> list[dict]:
    """Every usable music track with its mood tags, source and whether a credit line is required."""
    import json
    out = []
    man = INSTALL_ROOT / "packs" / "bgm" / "bgm.json"
    if man.exists():
        m = json.loads(man.read_text())
        for k, t in m["tracks"].items():
            out.append({"ref": f"lib:bgm/{k}", "title": t["title"], "mood": t["mood"], "tempo": t.get("tempo"),
                        "source": "bundled (Kevin MacLeod, CC BY 4.0)", "credit_required": True})
    if tier == "pro":
        for f in sorted((PRO_ROOT / "packs" / "bgm").glob("*")) if (PRO_ROOT / "packs" / "bgm").is_dir() else []:
            if f.suffix.lower() in EXTS["bgm"]:
                out.append({"ref": f"lib:bgm/{f.stem}", "title": f.stem, "mood": ["acoustic", "nhẹ nhàng", "sức khoẻ"],
                            "source": "pro pack", "credit_required": False})
    if workspace and (workspace / "library" / "bgm").is_dir():
        for d in sorted((workspace / "library" / "bgm").iterdir()):
            meta = d / "meta.json" if d.is_dir() else None
            info = json.loads(meta.read_text()) if meta and meta.exists() else {}
            out.append({"ref": f"lib:bgm/{d.stem if d.is_file() else d.name}", "title": info.get("title", d.stem),
                        "mood": info.get("mood", []), "source": info.get("source", "library"),
                        "credit_required": bool(info.get("credit"))})
    return out


def fetch_bgm(ctx, intent: str, name: str | None = None) -> dict:
    """HeyGen catalog (needs Node + `npx hyperframes auth login`): search by mood, save into
    <workspace>/library/bgm/<name>/ with meta.json. Free catalog tracks, ~28 s, used under the account's terms."""
    import json
    import os
    import re
    import shutil
    from nve.env import HYPERFRAMES_VERSION
    from nve.util import run
    if not ctx.workspace:
        raise NveError("No workspace.")
    if not ctx.env.get("node"):
        raise NveError("HeyGen music needs Node >= 22 (not available here). Use a bundled track: nve assets list bgm")
    tmp = ctx.workspace / ".nve" / "media"
    tmp.mkdir(parents=True, exist_ok=True)
    from nve.env import npx
    r = npx(ctx.env["node"], ["media-use", "resolve", "--type", "bgm", "--intent", intent, "--project", str(tmp), "--json"],
            timeout=600)
    text = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        if re.search(r"auth|login|unauthor", text, re.I):
            raise NveError("Not signed in to HeyGen. Run yourself: npx hyperframes@0.9.23 auth login")
        raise NveError("HeyGen search failed: " + text.strip().splitlines()[-1][:200] if text.strip() else "HeyGen search failed")
    files = sorted((tmp / ".media" / "audio" / "bgm").glob("*.*"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise NveError("HeyGen returned no track for that mood; try other words.")
    src = files[-1]
    slug = name or re.sub(r"[^a-z0-9]+", "-", intent.lower()).strip("-")[:30] or "track"
    dest = ctx.workspace / "library" / "bgm" / f"heygen-{slug}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest / src.name)
    meta = {"title": f"HeyGen: {intent}", "mood": [intent], "source": "HeyGen catalog (account terms; do not redistribute)",
            "credit": None, "intent": intent}
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return {"ref": f"lib:bgm/heygen-{slug}", "file": str(dest / src.name), "note": "~28 s track: nve loops it to the video length."}
