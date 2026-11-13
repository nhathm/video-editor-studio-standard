"""Vietnamese font pack (all SIL OFL, from github.com/google/fonts). `nve fonts sync` downloads
them into INSTALL_ROOT/packs/fonts/<Family>/ (a build-time step; the files ship in the bundles)."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from nve.paths import INSTALL_ROOT, NveError
from nve.util import log

RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/{dir}/{file}"
API = "https://api.github.com/repos/google/fonts/contents/ofl/{dir}"


def manifest() -> dict:
    return json.loads((INSTALL_ROOT / "packs" / "fonts" / "fonts.json").read_text())


def _list(dir_: str) -> list[str]:
    with urllib.request.urlopen(API.format(dir=dir_), timeout=30) as r:
        return [x["name"] for x in json.loads(r.read()) if x["name"].endswith((".ttf",)) or x["name"] == "OFL.txt"]


STATIC = {"Regular": 400, "Bold": 700, "Black": 900}


def make_static(dest: Path, family: str) -> list[str]:
    """libass cannot pick a weight from a variable font (it uses the default instance, often Thin),
    so build static Regular/Bold/Black files for the ffmpeg/ASS engine. Needs fontTools (build time only)."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
    except ImportError:
        log("fontTools not installed: static font instances not built (ASS engine will look thin)")
        return []
    made = []
    for var in dest.glob("*[[]*wght*[]].ttf"):
        if "Italic" in var.name:
            continue
        axes = TTFont(var)["fvar"].axes
        axis = next(a for a in axes if a.axisTag == "wght")
        others = {a.axisTag: a.defaultValue for a in axes if a.axisTag != "wght"}
        for style, w in STATIC.items():
            if not axis.minValue <= w <= axis.maxValue:
                continue
            out = dest / f"{family.replace(' ', '')}-{style}.ttf"
            if out.exists():
                made.append(out.name)
                continue
            f = instancer.instantiateVariableFont(TTFont(var), {"wght": w, **others})
            f["OS/2"].usWeightClass = w
            f["OS/2"].fsSelection = (f["OS/2"].fsSelection & ~0b1100001) | (0b100000 if w >= 700 else 0b1000000)
            f["head"].macStyle = 1 if w >= 700 else 0
            name = f["name"]
            name.setName(family if style in ("Regular", "Bold") else f"{family} {style}", 1, 3, 1, 0x409)
            name.setName("Bold" if style == "Bold" else "Regular", 2, 3, 1, 0x409)
            name.setName(family, 16, 3, 1, 0x409)
            name.setName(style, 17, 3, 1, 0x409)
            name.setName(f"{family} {style}", 4, 3, 1, 0x409)
            name.setName(f"{family.replace(' ', '')}-{style}", 6, 3, 1, 0x409)
            f.save(out)
            made.append(out.name)
    return made


def sync(only: list[str] | None = None) -> dict:
    res = {}
    for fam in manifest()["families"]:
        if only and fam["family"] not in only:
            continue
        dest = INSTALL_ROOT / "packs" / "fonts" / fam["family"].replace(" ", "")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            files = [f for f in _list(fam["dir"]) if "Italic" not in f or fam.get("italic")]
        except Exception as e:
            res[fam["family"]] = f"error: {e}"
            continue
        got = []
        for f in files:
            p = dest / f
            if not p.exists():
                with urllib.request.urlopen(RAW.format(dir=fam["dir"], file=urllib.request.quote(f)), timeout=60) as r:
                    p.write_bytes(r.read())
            got.append(f)
        got += make_static(dest, fam["family"])
        log(f"font {fam['family']}: {len(got)} files")
        res[fam["family"]] = got
    if not res:
        raise NveError("No fonts matched.")
    return res
