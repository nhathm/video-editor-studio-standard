"""Where things live.

INSTALL_ROOT holds everything nve ships (core, templates, blocks, packs, pro/). It is read-only
for users. The same layout is used in the git repo, the Claude Code plugin and the cloud skill
bundle, because core/nve/paths.py is always two levels below the install root.

WORKSPACE is the user's own folder (studio.json, .env, custom/, library/, projects/). nve never
writes into INSTALL_ROOT at runtime.
"""
from __future__ import annotations

import os
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parents[2]
PRO_ROOT = INSTALL_ROOT / "pro"
WORKSPACE_MARKERS = ("studio.json", "studio.yaml")
DEFAULT_WORKSPACE = Path("~/nve-studio")


def remembered_workspace_file() -> Path:
    """~/.nve/workspace holds the path of the last `nve init`, so /nve works from any folder."""
    return Path.home() / ".nve" / "workspace"


def remember_workspace(ws: Path) -> None:
    f = remembered_workspace_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(str(ws) + "\n", encoding="utf-8")


class NveError(Exception):
    """An error meant for the user: printed without a traceback."""


def find_workspace(start: Path | None = None) -> Path | None:
    env = os.environ.get("NVE_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    p = (start or Path.cwd()).resolve()
    for d in (p, *p.parents):
        if any((d / m).exists() for m in WORKSPACE_MARKERS):
            return d
    # Not inside a workspace: fall back to the one `nve init` remembered.
    try:
        r = Path(remembered_workspace_file().read_text(encoding="utf-8").strip()).expanduser()
    except OSError:
        return None
    return r.resolve() if any((r / m).exists() for m in WORKSPACE_MARKERS) else None


def require_workspace(start: Path | None = None) -> Path:
    ws = find_workspace(start)
    if ws is None:
        raise NveError("No nve workspace here. Run `nve init <folder>` first (or set NVE_WORKSPACE).")
    if is_inside_install(ws):
        raise NveError(f"The workspace must not be inside the nve install folder ({INSTALL_ROOT}).")
    return ws


def is_inside_install(p: Path) -> bool:
    try:
        Path(p).resolve().relative_to(INSTALL_ROOT)
        return True
    except ValueError:
        return False


def project_dir(ws: Path, name: str) -> Path:
    p = Path(name)
    if p.is_absolute() or (p.exists() and p.is_dir() and (p / "project.json").exists()):
        return p.resolve()
    return (ws / "projects" / name).resolve()
