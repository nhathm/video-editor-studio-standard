"""S0 Doctor: detect where nve runs and what it can use. Cached in <workspace>/.nve/env.json.

Fast by design (no npx by default). `--deep` also asks the HyperFrames CLI for its auth status,
which takes a couple of seconds. On the cloud runtime (claude.ai) it also checks, in a few seconds,
whether the sandbox may reach the domains nve downloads from (account-level network allowlist).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from nve import __version__
from nve.paths import INSTALL_ROOT, PRO_ROOT
from nve.util import dump_json, run

CACHE_TTL = 24 * 3600
# Domains a claude.ai sandbox must be allowed to reach (Settings > Capabilities > Additional allowed domains).
# api.elevenlabs.io: Scribe transcripts. huggingface.co / *.huggingface.co / *.hf.co: whisper model files.
ALLOWLIST_DOMAINS = ["api.elevenlabs.io", "huggingface.co", "*.huggingface.co", "*.hf.co"]
NET_PROBES = {"api.elevenlabs.io": "https://api.elevenlabs.io/v1/models",
              "huggingface.co": "https://huggingface.co/api/models/Systran/faster-whisper-small",
              "github.com": "https://github.com"}


def probe_url(url: str, timeout: float = 6) -> bool:
    """True when the host answers at all. A sandbox egress proxy refuses blocked hosts with 403 or a
    failed tunnel; a real API answers 200/401/404 (401 = reachable, just no key)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout):
            return True
    except urllib.error.HTTPError as e:
        return e.code != 403
    except Exception:  # noqa: BLE001  (URLError, timeout, tunnel refused)
        return False


def check_network() -> dict:
    return {host: probe_url(url) for host, url in NET_PROBES.items()}
HYPERFRAMES_VERSION = "0.9.23"


def detect_runtime() -> str:
    if Path("/mnt/user-data").exists() or Path("/mnt/skills").exists() or Path("/home/claude").is_dir():
        return "cloud"
    if os.environ.get("CLAUDECODE") == "1" or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    return "shell"


def _version(cmd: list[str], pattern: str) -> str | None:
    try:
        r = run(cmd, check=False, timeout=10)
    except Exception:
        return None
    m = re.search(pattern, (r.stdout or "") + (r.stderr or ""))
    return m.group(1) if m else None


def find_node() -> dict | None:
    """Newest node >= 22: PATH first, then nvm installs (the login shell may default to an old one)."""
    cands = []
    p = shutil.which("node")
    if p:
        cands.append(Path(p))
    nvm = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm")) / "versions" / "node"
    if nvm.is_dir():
        cands += sorted(nvm.glob("v*/bin/node"))
    best = None
    for c in cands:
        v = _version([str(c), "--version"], r"v(\d+\.\d+\.\d+)")
        if v and int(v.split(".")[0]) >= 22 and (best is None or tuple(map(int, v.split("."))) > tuple(map(int, best["version"].split(".")))):
            best = {"path": str(c), "bin_dir": str(c.parent), "version": v}
    return best


def read_dotenv(ws: Path | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if ws and (ws / ".env").exists():
        for line in (ws / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_key(name: str, ws: Path | None) -> str | None:
    return os.environ.get(name) or read_dotenv(ws).get(name) or None


def detect_edition() -> dict:
    """Public exports carry EDITION.json (tier standard/newbie; `resources`: models the edition may fetch from
    its own mirror, Newbie only).
    Without it: the private repo (has pro/) is Pro, anything else Standard."""
    f = INSTALL_ROOT / "EDITION.json"
    if f.exists():
        try:
            ed = json.loads(f.read_text())
            if ed.get("tier"):
                return ed
        except (OSError, ValueError):
            pass
    tier = "pro" if (PRO_ROOT / "LICENSES.json").exists() or (PRO_ROOT / "packs").is_dir() else "standard"
    return {"tier": tier}


def _npmrc_prefix() -> str | None:
    f = Path.home() / ".npmrc"
    try:
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "prefix" and v.strip():
                return os.path.expanduser(v.strip())
    except OSError:
        pass
    return None


def npx(node: dict, args: list[str], *, timeout: float = 3600, check: bool = False):
    """Run `npx hyperframes@<pinned> <args>` (all path args must be absolute).
    Runs from a neutral temp folder: on claude.ai a ~/.npmrc that sets `prefix` becomes "project config"
    when the cwd is the home folder, and npm refuses ("prefix cannot be changed from project config")."""
    import tempfile
    env = {**os.environ, "PATH": node["bin_dir"] + os.pathsep + os.environ.get("PATH", "")}
    prefix = _npmrc_prefix()
    if prefix and "npm_config_prefix" not in env:
        env["npm_config_prefix"] = prefix
    cwd = Path(tempfile.gettempdir()) / "nve-npx"
    cwd.mkdir(parents=True, exist_ok=True)
    return run(["npx", "-y", f"hyperframes@{HYPERFRAMES_VERSION}", *args], env=env, cwd=cwd, timeout=timeout, check=check)


def doctor(ws: Path | None, refresh: bool = False, deep: bool = False) -> dict:
    cache = ws / ".nve" / "env.json" if ws else None
    if cache and cache.exists() and not refresh and not deep:
        data = json.loads(cache.read_text())
        if time.time() - data.get("checked_at", 0) < CACHE_TTL and data.get("nve_version") == __version__:
            data["cached"] = True
            return data

    runtime = detect_runtime()
    tools = {
        "ffmpeg": _version(["ffmpeg", "-version"], r"ffmpeg version (\S+)"),
        "ffprobe": _version(["ffprobe", "-version"], r"ffprobe version (\S+)"),
        "libass": None,
        "whisper": shutil.which("whisper-cli") or shutil.which("whisper-cpp"),
    }
    from nve import pro
    tools["yt-dlp"] = pro.load("download").ytdlp_version() if pro.available() else None
    if tools["ffmpeg"]:
        r = run(["ffmpeg", "-hide_banner", "-filters"], check=False)
        tools["libass"] = " subtitles " in (r.stdout or "")
    node = find_node()
    try:
        import cv2  # noqa: F401
        opencv = True
    except Exception:
        opencv = False

    keys = {"elevenlabs": bool(get_key("ELEVENLABS_API_KEY", ws))}
    heygen = None
    if deep and node:
        r = npx(node, ["auth", "status"], timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        heygen = bool(re.search(r"logged in|authenticated|valid", out, re.I)) and not re.search(r"not logged|expired", out, re.I)
    keys["heygen"] = heygen
    network = check_network() if runtime == "cloud" or deep else None

    caps = {
        "transcribe.scribe": keys["elevenlabs"],
        "transcribe.whisper": bool(node) or bool(tools["whisper"]),
        "compose.hyperframes": bool(node),
        "compose.ass": bool(tools["ffmpeg"]) and bool(tools["libass"]),
        "grade.numpy": opencv,
        "grade.ffmpeg": bool(tools["ffmpeg"]),
    }
    edition = detect_edition()
    reach = lambda host: network is None or network.get(host, True)  # noqa: E731
    captions = []
    if keys["elevenlabs"] and reach("api.elevenlabs.io"):
        captions.append("scribe")
    if reach("huggingface.co"):
        captions.append("whisper")
    from importlib.util import find_spec
    if "whisper-small" in (edition.get("resources") or []) and find_spec("nve.resources") and reach("github.com"):
        captions.append("whisper-git")
    level = "L0" + ("+elevenlabs" if keys["elevenlabs"] else "") + ("+heygen" if heygen else "")
    data = {"nve_version": __version__, "checked_at": int(time.time()), "runtime": runtime,
            "install_root": str(INSTALL_ROOT), "workspace": str(ws) if ws else None,
            "edition": edition, "captions": captions, "tools": tools, "node": node, "opencv": opencv,
            "keys": keys, "network": network, "capabilities": caps, "level": level, "cached": False}
    if cache:
        dump_json(cache, data)
    return data


def format_report(d: dict) -> str:
    ok = lambda b: "ok " if b else ("?  " if b is None else "-- ")  # noqa: E731
    t, k = d["tools"], d["keys"]
    lines = [
        f"nve {d['nve_version']}  runtime={d['runtime']}  edition={d['edition']['tier']}  level={d['level']}"
        + ("  (cached)" if d.get("cached") else ""),
        f"  {ok(t['ffmpeg'])} ffmpeg {t['ffmpeg'] or 'MISSING (required)'}",
        f"  {ok(t['libass'])} libass subtitles filter (compose.ass fallback)",
        f"  {ok(d['node'])} node >=22 {d['node']['version'] if d['node'] else 'missing -> HyperFrames unavailable, using ffmpeg/ASS'}",
        f"  {ok(d['opencv'])} opencv (skin retouch; without it the look uses an ffmpeg approximation)",
        *([f"  {ok(t.get('yt-dlp'))} yt-dlp {t.get('yt-dlp') or 'missing -> reference links cannot be downloaded (send the file instead)'}"]
          if d["tools"].get("yt-dlp") is not None or (PRO_ROOT / "python" / "nve_pro").is_dir() else []),
        f"  {ok(k['elevenlabs'])} ElevenLabs key {'set' if k['elevenlabs'] else 'not set -> whisper transcripts (run: nve connect elevenlabs)'}",
        f"  {ok(k['heygen'])} HeyGen login {'' if k['heygen'] is not None else '(not checked; nve doctor --deep)'}",
    ]
    net = d.get("network")
    if net is not None:
        for host, reachable in net.items():
            lines.append(f"  {ok(reachable)} network {host} {'reachable' if reachable else 'BLOCKED'}")
        caps = d.get("captions")
        if caps == []:
            # Typical of the claude.ai Free plan: only package hosts are reachable and domains cannot be added.
            lines.append("  -> no automatic captions here: paste the spoken words to make captions.")
            if (d.get("edition") or {}).get("tier") == "standard":
                lines.append("     (with Claude Pro you can allow the download hosts and get automatic captions)")
        elif caps == ["whisper-git"]:
            lines.append("  -> captions: whisper model from the GitHub mirror (Hugging Face blocked)")
        if not all(v for h, v in net.items() if h != "github.com") and caps != ["whisper-git"]:
            lines.append("  -> Claude Pro or higher: Settings > Capabilities (web or desktop app) > Additional allowed domains: "
                         + ", ".join(ALLOWLIST_DOMAINS) + ". Account-wide; then start a new chat.")
    return "\n".join(lines)
