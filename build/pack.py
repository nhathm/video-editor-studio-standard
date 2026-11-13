#!/usr/bin/env python3
"""Build the claude.ai (cloud) skill zips from editions/*.json.

    python3 build/pack.py cloud-pro        -> dist/nve-cloud-pro-<version>.zip
    python3 build/pack.py cloud-standard   -> dist/nve-cloud-standard-<version>.zip

The zip holds ONE folder `nve/` that is self-contained: SKILL.md + references + bin at its root, and the
engine and data next to them (core/nve, templates, blocks, packs, engines.json [, pro]). nve's
INSTALL_ROOT resolves to that folder, exactly like the repo root locally.
Local editions need no build: the repo itself is the Claude Code plugin.
"""
from __future__ import annotations

import fnmatch
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = ["__pycache__", "*.pyc", ".DS_Store", "tests", ".gitkeep"]
# claude.ai sandboxes usually lack Chrome, so the ASS engine renders: it only needs the static font
# instances. The variable fonts stay for HyperFrames when it is available.


def version() -> str:
    for line in (ROOT / "core" / "nve" / "__init__.py").read_text().splitlines():
        if line.startswith("__version__"):
            return line.split('"')[1]
    return "0.0.0"


def copy(src: Path, dst: Path) -> None:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP), dirs_exist_ok=True)


def build(edition: str) -> Path:
    ed = json.loads((ROOT / "editions" / f"{edition}.json").read_text())
    if ed["runtime"] != "cloud":
        sys.exit(f"{edition} is a local edition: the git repo itself is the plugin, nothing to pack.")
    out = ROOT / "dist" / edition
    if out.exists():
        shutil.rmtree(out)
    skill = out / "nve"
    copy(ROOT / "skills" / "nve", skill)                      # SKILL.md, references/, bin/
    for item in ("core/nve", "templates/core", "blocks/core", "packs", "engines.json"):
        copy(ROOT / item, skill / item)
    if ed["tier"] == "pro":
        copy(ROOT / "pro", skill / "pro")
    # leak check for Standard
    if ed["tier"] != "pro":
        bad = [p for p in skill.rglob("*") if p.is_file() and ("pro/" in str(p.relative_to(skill)) or p.name == ".env")]
        if bad:
            sys.exit(f"Standard bundle would contain private files: {bad[:5]}")
    (skill / "EDITION.json").write_text(json.dumps({"edition": edition, "tier": ed["tier"], "version": version()}, indent=2))
    zpath = ROOT / "dist" / f"nve-{edition}-{version()}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and not any(fnmatch.fnmatch(part, pat) for part in p.parts for pat in SKIP):
                info = zipfile.ZipInfo.from_file(p, p.relative_to(out).as_posix())
                if p.name == "nve" and p.parent.name == "bin":
                    info.external_attr = 0o100755 << 16
                with p.open("rb") as f:
                    z.writestr(info, f.read(), zipfile.ZIP_DEFLATED)
    print(f"{zpath.relative_to(ROOT)}  {zpath.stat().st_size / 1e6:.1f} MB")
    return zpath


if __name__ == "__main__":
    for e in sys.argv[1:] or ["cloud-pro", "cloud-standard"]:
        build(e)
