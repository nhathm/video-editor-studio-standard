"""Large resources fetched on demand (models first), listed in <install>/resources.json.

Each entry pins a git repo folder and the SHA-256 of every file. Fetching uses only github.com (git), so it
works on the claude.ai Free sandbox where Hugging Face, release assets, LFS and raw.githubusercontent.com are
blocked:

    git clone --depth 1 --filter=blob:none --sparse <repo>    (no file contents yet)
    git sparse-checkout set <path>                             (downloads only that folder)

and falls back to a plain shallow clone when the server or git cannot do partial clones. Big files are stored
as <50 MB parts and joined here. The result is cached in ~/.cache/nve/<id>/<version> (one sandbox = one chat
on claude.ai, so there the cache lasts one conversation; on a computer it lasts).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from nve.paths import INSTALL_ROOT, NveError
from nve.util import log, retry_once

CATALOG = INSTALL_ROOT / "resources.json"


def catalog() -> dict:
    try:
        return {k: v for k, v in json.loads(CATALOG.read_text()).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def entry(rid: str) -> dict:
    e = catalog().get(rid)
    if not e:
        raise NveError(f"Unknown resource '{rid}' (not in resources.json)")
    return e


def cache_dir(rid: str) -> Path:
    return Path.home() / ".cache" / "nve" / rid / entry(rid)["version"]


def is_cached(rid: str) -> bool:
    try:
        d = cache_dir(rid)
    except NveError:
        return False
    return (d / ".verified").exists()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: list[str], cwd: Path | None = None, timeout: float = 1200) -> None:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "git failed").strip()[-200:])


def _clone(repo: str, path: str, dst: Path) -> str:
    """Sparse partial clone of one folder; plain shallow clone if that is not possible. Returns the method."""
    shutil.rmtree(dst, ignore_errors=True)
    try:
        _git(["clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", repo, str(dst)])
        _git(["sparse-checkout", "set", path], cwd=dst)
        if (dst / path).is_dir():
            return "sparse"
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        log(f"partial clone not possible ({str(e)[:80]}); cloning the whole repo")
    shutil.rmtree(dst, ignore_errors=True)
    _git(["clone", "-q", "--depth", "1", repo, str(dst)])
    return "full"


def fetch(rid: str) -> Path:
    """Folder with the verified files of resource `rid` (fetched once, then cached)."""
    e = entry(rid)
    dst = cache_dir(rid)
    if (dst / ".verified").exists():
        return dst
    repo = os.environ.get("NVE_RESOURCES_REPO") or e["repo"]
    t0 = time.time()
    tmp = dst.parent / f".{e['version']}.clone"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    holder = {}

    def attempt():
        holder["method"] = _clone(repo, e["path"], tmp)
    try:
        retry_once(attempt, f"git clone {rid}")
    except Exception as err:  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        raise NveError(f"could not fetch {rid} from {repo} (twice): {err}") from err
    src = tmp / e["path"]
    files, joins = e["files"], e.get("join", {})
    parts = {p for ps in joins.values() for p in ps}
    try:
        for name, digest in files.items():
            if name in joins:
                continue
            if not (src / name).exists() or _sha256(src / name) != digest:
                raise NveError(f"{rid}: {name} missing or checksum mismatch")
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for name in files:
            if name not in joins and name not in parts:
                shutil.copy2(src / name, dst / name)
        for name, ps in joins.items():
            with open(dst / name, "wb") as out:
                for p in ps:
                    with open(src / p, "rb") as f:
                        shutil.copyfileobj(f, out, 1 << 22)
            if _sha256(dst / name) != files[name]:
                raise NveError(f"{rid}: joined {name} checksum mismatch")
    except NveError:
        shutil.rmtree(dst, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    (dst / ".verified").write_text(json.dumps({"version": e["version"], "method": holder.get("method"),
                                               "seconds": round(time.time() - t0, 1)}) + "\n")
    log(f"{rid} {e['version']} ready ({holder.get('method')} clone, {time.time() - t0:.0f}s)")
    return dst
