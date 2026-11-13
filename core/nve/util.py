"""Small shared helpers: JSON/YAML IO, ffprobe, subprocess, logging."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from nve.paths import NveError


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mts"}


def log(msg: str) -> None:
    print(f"[nve] {msg}", file=sys.stderr)


def load_data(path: Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise NveError(f"{path.name} is YAML but PyYAML is not installed; use JSON or `pip install pyyaml`.") from e
        return yaml.safe_load(text)
    return json.loads(text)


def dump_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None


def run(cmd: list[str], *, check: bool = True, capture: bool = True, env: dict | None = None, cwd: Path | None = None,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=capture, text=True, env=env, cwd=cwd, timeout=timeout)
    except FileNotFoundError as e:
        raise NveError(f"Command not found: {cmd[0]}") from e
    if check and r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-15:]
        raise NveError(f"`{Path(str(cmd[0])).name} ...` failed ({r.returncode}):\n" + "\n".join(tail))
    return r


def retry_once(fn, what: str, on: tuple[type[BaseException], ...] = (Exception,)):
    """Run fn(); if it raises one of `on`, log and run it exactly once more (installs, downloads, network
    calls). A second failure propagates: the caller reports it, nothing loops. Other errors are not retried."""
    try:
        return fn()
    except on as e:
        log(f"{what} failed ({str(e).strip().splitlines()[-1][:160] if str(e).strip() else type(e).__name__}); retrying once")
        return fn()


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def ffprobe(path: Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    return json.loads(r.stdout)


def media_info(path: Path) -> dict:
    """Normalised facts about one source file (video, image or audio)."""
    d = ffprobe(path)
    v = next((s for s in d["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in d["streams"] if s.get("codec_type") == "audio"), None)
    fmt = d.get("format", {})
    is_image = Path(path).suffix.lower() in IMAGE_EXT
    info: dict[str, Any] = {"path": str(path), "kind": "image" if is_image else ("video" if v else "audio"),
                            "duration": round(float(fmt.get("duration") or 0), 3), "has_audio": a is not None}
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if abs(rot) in (90, 270):
            w, h = h, w
        num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 0.0
        trc = v.get("color_transfer", "") or ""
        info.update({"width": w, "height": h, "fps": round(fps, 3), "codec": v.get("codec_name"),
                     "hdr": trc in ("arib-std-b67", "smpte2084"), "color_transfer": trc,
                     "vfr": v.get("r_frame_rate") != v.get("avg_frame_rate")})
    return info


def duration(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip() or 0)
