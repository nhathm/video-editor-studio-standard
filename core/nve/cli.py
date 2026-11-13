"""nve command line. Every command prints JSON on stdout (for Claude) and progress on stderr."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nve import __version__, registry
from nve.engines import Ctx, _registry, chain
from nve.paths import INSTALL_ROOT, NveError, find_workspace, is_inside_install, project_dir, require_workspace
from nve.util import dump_json


def out(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _ctx(need_ws: bool = True) -> Ctx:
    from nve.env import doctor
    ws = require_workspace() if need_ws else find_workspace()
    return Ctx(env=doctor(ws), workspace=ws)


def _prj(ctx: Ctx, name: str):
    from nve.project import Project
    prj = Project(project_dir(ctx.workspace, name))
    ctx.project = prj
    if prj.storyboard_path.exists():
        try:
            ctx.storyboard = prj.load_storyboard()
        except Exception:
            pass
    return prj


def cmd_init(a):
    ws = Path(a.dir).expanduser().resolve()
    if is_inside_install(ws):
        raise NveError("Create the workspace outside the nve install folder.")
    for d in ("custom/templates", "custom/blocks", "custom/scripts", "custom/fonts", "custom/brands", "custom/skills",
              "library/sfx", "library/bgm", "library/img", "projects", ".nve"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    if not (ws / "studio.json").exists():
        dump_json(ws / "studio.json", {"schema": "nve.studio/1", "language": "vi", "default_template": "core:talking-head",
                                       "engines": {}, "brand": None})
    if not (ws / ".env").exists():
        (ws / ".env").write_text("# Paste your own keys here. nve never prints this file.\nELEVENLABS_API_KEY=\n")
    (ws / "custom" / "README.md").write_text(
        "# custom/\n\nYour own templates, blocks, scripts, fonts and brand kits. nve updates never touch this folder.\n"
        "Code Claude writes for you lands in custom/scripts/<name>/ (reusable) or projects/<p>/work/scripts/ (one-off).\n")
    out({"workspace": str(ws)})


def cmd_doctor(a):
    from nve.env import doctor, format_report
    ws = find_workspace()
    d = doctor(ws, refresh=a.refresh or a.deep, deep=a.deep)
    if a.json:
        out(d)
    else:
        print(format_report(d))
        if not ws:
            print("  (no workspace found: run `nve init <folder>`)")


def cmd_new(a):
    from nve.project import create
    ws = require_workspace()
    prj = create(ws, [Path(f) for f in a.files], a.name, a.move)
    out({"project": str(prj.path), "sources": prj.meta["sources"]})


def cmd_ingest(a):
    from nve.stages import ingest
    ctx = _ctx()
    out(ingest(_prj(ctx, a.project), ctx, a.language, "no" if a.no_transcribe else "auto"))


def cmd_transcript(a):
    from nve import stages
    ctx = _ctx()
    prj = _prj(ctx, a.project)
    if a.action == "show":
        out(stages.transcript_show(prj, a.src))
    else:
        out(stages.transcript_check(prj, ctx))


def cmd_shots(a):
    from nve.stages import analyze_shots
    ctx = _ctx()
    res = analyze_shots(_prj(ctx, a.project))
    out({"shots": len(res["shots"]), "sheets": res["sheets"], "file": "analysis/shots.json"})


def cmd_plan(a):
    from nve import stages
    ctx = _ctx()
    prj = _prj(ctx, a.project)
    if a.action == "draft":
        stages.plan_draft(prj, ctx, a.template, a.strategy, a.overwrite)
    res = stages.refresh(prj, ctx)
    res.update({"storyboard": str(prj.storyboard_path), "markdown": str(prj.p("storyboard.md")),
                "words_out": str(prj.p("analysis", "words_out.json"))})
    out(res)


def cmd_preview(a):
    from nve.stages import preview
    ctx = _ctx()
    times = [float(x) for x in a.at.split(",")] if a.at else None
    out(preview(_prj(ctx, a.project), ctx, times))


def cmd_approve(a):
    from nve.stages import approve
    ctx = _ctx()
    out({"gates": approve(_prj(ctx, a.project), a.gate, a.reopen)})


def cmd_render(a):
    from nve.stages import render
    ctx = _ctx()
    out(render(_prj(ctx, a.project), ctx, a.force, a.phone))


def cmd_qc(a):
    from nve.stages import qc
    ctx = _ctx()
    prj = _prj(ctx, a.project)
    out(qc(prj, prj.p(a.video) if not Path(a.video).is_absolute() else Path(a.video), ctx.storyboard))


def cmd_template(a):
    ws = find_workspace()
    if a.action == "list":
        out([{"id": i, "label": it.data.get("label"), "cut_strategy": it.data.get("cut_strategy"),
              "extends": it.data.get("extends")} for i, it in registry.scan("template", ws).items()])
    elif a.action == "show":
        out(registry.resolve(a.id, "template", ws))
    elif a.action == "fork":
        if not ws:
            raise NveError("No workspace.")
        out({"created": str(registry.fork(a.id, "template", a.name, ws))})


def cmd_block(a):
    ws = find_workspace()
    out([{"id": i, "label": it.data.get("label"), "engines": it.data.get("engines"), "props": list(it.data.get("props", {}))}
         for i, it in registry.scan("block", ws).items()])


def cmd_assets(a):
    from nve.assets import fetch_bgm, list_assets
    from nve.env import detect_edition
    if a.action == "fetch-bgm":
        if not a.intent:
            raise NveError("--intent is required, e.g. --intent \"upbeat, playful, no vocals\"")
        out(fetch_bgm(_ctx(), a.intent, a.name))
        return
    out(list_assets(a.type or "sfx", find_workspace(), detect_edition()["tier"], detail=True))


def cmd_engines(a):
    ctx = _ctx(need_ws=False)
    reg = _registry()
    res = {}
    for cap in ("transcribe", "cut", "key", "compose"):
        res[cap] = []
        for eid in chain(cap, ctx):
            cls = reg.get(f"{cap}.{eid}")
            ok, why = cls().available(ctx) if cls else (False, "not installed")
            res[cap].append({"engine": eid, "available": ok, "why": why})
    out(res)


def cmd_fonts(a):
    from nve.fonts import sync
    out(sync(a.only.split(",") if a.only else None))


def cmd_connect(a):
    from nve.env import ALLOWLIST_DOMAINS, detect_runtime
    cloud = detect_runtime() == "cloud"
    guides = {
        "elevenlabs": {
            "what": "Accurate word-level transcripts (keeps Vietnamese fillers), voice-over, generated SFX.",
            "steps": ["Sign in at https://elevenlabs.io", "Profile -> API Keys -> Create (a dedicated key with a low credit limit is safest)",
                      "Local: paste it into <workspace>/.env as ELEVENLABS_API_KEY=... yourself; never paste it in chat."
                      if not cloud else
                      "Cloud: prefer a claude.ai connector. Otherwise you may paste the key in chat AFTER reading the warning: it stays in this conversation's history."],
            "check": "nve doctor --refresh"},
        "heygen": {
            "what": "HeyGen catalog music/images, avatars (HyperFrames media-use).",
            "steps": ["Run: npx hyperframes@0.9.23 auth login  (opens the browser; sign in yourself)"],
            "check": "nve doctor --deep"},
        "network": {
            "what": "claude.ai only: let the sandbox reach ElevenLabs (Scribe) and Hugging Face (whisper models).",
            "steps": ["Open claude.ai in a web browser or the desktop app (the iOS app has no such field)",
                      "Settings -> Capabilities: 'Code execution and file creation' on",
                      "Additional allowed domains: add " + ", ".join(ALLOWLIST_DOMAINS),
                      "The list belongs to the account: chats opened on the phone use it too. Start a new chat."],
            "check": "nve doctor --refresh"},
    }
    if a.provider not in guides:
        raise NveError(f"Unknown provider. Known: {', '.join(guides)}")
    out(guides[a.provider])


def cmd_where(a):
    out({"install_root": str(INSTALL_ROOT), "workspace": str(find_workspace() or ""), "version": __version__})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="nve", description="nve-studio video editing engine")
    ap.add_argument("--version", action="version", version=__version__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("init", help="create a workspace folder"); p.add_argument("dir"); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("doctor", help="S0: check the environment")
    p.add_argument("--refresh", action="store_true"); p.add_argument("--deep", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_doctor)
    p = sp.add_parser("new", help="create a project from video/photo files")
    p.add_argument("files", nargs="+"); p.add_argument("--name"); p.add_argument("--move", action="store_true"); p.set_defaults(fn=cmd_new)
    p = sp.add_parser("ingest", help="S1: probe sources, transcribe, measure signals")
    p.add_argument("project"); p.add_argument("--language"); p.add_argument("--no-transcribe", action="store_true"); p.set_defaults(fn=cmd_ingest)
    p = sp.add_parser("transcript", help="proof-read a transcript: show numbered words / check the corrections file")
    p.add_argument("action", choices=["show", "check"]); p.add_argument("project"); p.add_argument("--src")
    p.set_defaults(fn=cmd_transcript)
    p = sp.add_parser("shots", help="split videos into shots, score them, write contact sheets")
    p.add_argument("project"); p.set_defaults(fn=cmd_shots)
    p = sp.add_parser("plan", help="S3: draft or refresh the storyboard")
    p.add_argument("action", choices=["draft", "refresh"]); p.add_argument("project")
    p.add_argument("--template"); p.add_argument("--strategy", choices=["speech", "visual", "beat", "hybrid"])
    p.add_argument("--overwrite", action="store_true"); p.set_defaults(fn=cmd_plan)
    p = sp.add_parser("preview", help="S4: stills with look + text applied")
    p.add_argument("project"); p.add_argument("--at", help="comma-separated output times"); p.set_defaults(fn=cmd_preview)
    p = sp.add_parser("approve", help="record a gate the user approved")
    p.add_argument("project"); p.add_argument("gate", choices=["plan", "preview", "final"]); p.add_argument("--reopen", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sp.add_parser("render", help="S5-S9: cut, compose, render, cover, QC")
    p.add_argument("project"); p.add_argument("--force", action="store_true", help="user said render right away (skip gates)")
    p.add_argument("--phone", action="store_true", help="also write a smaller _phone copy"); p.set_defaults(fn=cmd_render)
    p = sp.add_parser("qc", help="S9: check a rendered file"); p.add_argument("project"); p.add_argument("video"); p.set_defaults(fn=cmd_qc)
    p = sp.add_parser("template", help="list/show/fork templates")
    p.add_argument("action", choices=["list", "show", "fork"]); p.add_argument("id", nargs="?"); p.add_argument("name", nargs="?")
    p.set_defaults(fn=cmd_template)
    p = sp.add_parser("block", help="list blocks"); p.set_defaults(fn=cmd_block)
    p = sp.add_parser("assets", help="list assets, or fetch a HeyGen catalog track into the library")
    p.add_argument("action", choices=["list", "fetch-bgm"]); p.add_argument("type", nargs="?", choices=["sfx", "bgm", "img", "lottie"])
    p.add_argument("--intent", help="fetch-bgm: mood in words"); p.add_argument("--name", help="fetch-bgm: library name")
    p.set_defaults(fn=cmd_assets)
    p = sp.add_parser("engines", help="show engine chains and availability"); p.set_defaults(fn=cmd_engines)
    p = sp.add_parser("fonts", help="download the Vietnamese font pack"); p.add_argument("action", choices=["sync"])
    p.add_argument("--only"); p.set_defaults(fn=cmd_fonts)
    p = sp.add_parser("connect", help="how to connect a provider"); p.add_argument("provider"); p.set_defaults(fn=cmd_connect)
    p = sp.add_parser("where", help="print install root and workspace"); p.set_defaults(fn=cmd_where)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except NveError as e:
        print(f"nve: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
