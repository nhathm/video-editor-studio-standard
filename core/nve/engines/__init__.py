"""Engines are adapters that plug into a capability socket (transcribe, cut, compose…).

The preference chain per capability comes from INSTALL_ROOT/engines.json, can be pinned per
workspace (studio.json "engines") or per storyboard ("engines"). The router tries each engine in
order: unavailable -> skip, failure -> fall back to the next, and says so in one line.
Adding an engine = one module here + one line in engines.json. Stages never name an engine.
"""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nve.paths import INSTALL_ROOT, NveError
from nve.util import log


class EngineUnavailable(Exception):
    pass


class EngineFailed(Exception):
    pass


@dataclass
class Ctx:
    env: dict
    workspace: Path | None
    project: Any = None          # nve.project.Project
    storyboard: dict | None = None
    notes: list[str] = field(default_factory=list)


class Engine:
    id = "base"
    capability = "none"

    def available(self, ctx: Ctx) -> tuple[bool, str]:
        return True, ""

    def run(self, job: dict, ctx: Ctx) -> dict:
        raise NotImplementedError


def _registry() -> dict[str, type[Engine]]:
    from nve.engines import compose_ass, compose_hyperframes, cut_ffmpeg, key, transcribe
    out: dict[str, type[Engine]] = {}
    for mod in (transcribe, cut_ffmpeg, key, compose_hyperframes, compose_ass):
        for e in mod.ENGINES:
            out[f"{e.capability}.{e.id}"] = e
    return out


def chain(capability: str, ctx: Ctx) -> list[str]:
    default = json.loads((INSTALL_ROOT / "engines.json").read_text())["chains"]
    pins = {}
    if ctx.workspace and (ctx.workspace / "studio.json").exists():
        pins.update(json.loads((ctx.workspace / "studio.json").read_text()).get("engines", {}))
    if ctx.storyboard:
        pins.update(ctx.storyboard.get("engines", {}))
    base = list(default.get(capability, []))
    if capability in pins:
        pinned = pins[capability]
        base = [pinned] + [e for e in base if e != pinned]
    return base


def run_capability(capability: str, job: dict, ctx: Ctx, only: str | None = None) -> dict:
    reg = _registry()
    tried = []
    for eid in ([only] if only else chain(capability, ctx)):
        cls = reg.get(f"{capability}.{eid}")
        if cls is None:
            tried.append(f"{eid}: not installed")
            continue
        eng = cls()
        ok, why = eng.available(ctx)
        if not ok:
            tried.append(f"{eid}: {why}")
            continue
        try:
            res = eng.run(job, ctx)
            if tried:
                msg = f"{capability}: used {eid} (skipped {'; '.join(tried)})"
                log(msg)
                ctx.notes.append(msg)
            res["engine"] = eid
            return res
        except (EngineFailed, EngineUnavailable, NveError) as e:
            tried.append(f"{eid} failed: {str(e).splitlines()[0] if str(e) else type(e).__name__}")
            log(f"{capability}.{eid} failed, falling back: {e}")
        except Exception as e:  # unexpected bug in an adapter: still fall back, but keep the trace
            tried.append(f"{eid} crashed: {e}")
            log(f"{capability}.{eid} crashed, falling back:\n{traceback.format_exc()}")
    raise NveError(f"No engine could do '{capability}'. Tried: " + "; ".join(tried))
