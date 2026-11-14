"""One video = one project folder:

projects/<slug>/
  project.json          meta (created, sources, template)
  source/               originals, never modified
  reference/            sample videos to analyse (only on request)
  analysis/             ingest.json, transcripts/<src>.json, shots/, words_out.json
  storyboard.json/.md   the plan (single source of truth)
  preview/              stills + sheet for gate G2
  work/                 intermediates (cut.mp4, words.json, motion/, scripts/ for one-off code)
  renders/              final_vN.mp4, final_vN_phone.mp4
  project.md            session log
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import unicodedata
from pathlib import Path

from nve.paths import NveError, is_inside_install
from nve.util import IMAGE_EXT, VIDEO_EXT, dump_json, log

SUBDIRS = ("source", "reference", "analysis/transcripts", "preview", "work/scripts", "renders")
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:40] or "video"


class Project:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        if not (self.path / "project.json").exists():
            raise NveError(f"{self.path} is not an nve project (no project.json).")
        if is_inside_install(self.path):
            raise NveError("Projects must live in the workspace, not inside the nve install folder.")

    # paths
    def p(self, *parts: str) -> Path:
        return self.path.joinpath(*parts)

    @property
    def meta(self) -> dict:
        return json.loads(self.p("project.json").read_text())

    def save_meta(self, meta: dict) -> None:
        dump_json(self.p("project.json"), meta)

    @property
    def storyboard_path(self) -> Path:
        return self.p("storyboard.json")

    def load_storyboard(self) -> dict:
        if not self.storyboard_path.exists():
            raise NveError("No storyboard yet. Run `nve plan draft <project>` first.")
        return json.loads(self.storyboard_path.read_text())

    def log(self, title: str, lines: list[str]) -> None:
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.p("project.md").open("a", encoding="utf-8") as f:
            f.write(f"\n## {stamp} · {title}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n")

    def next_render_name(self, stem: str = "final") -> str:
        n = 1
        while self.p("renders", f"{stem}_v{n}.mp4").exists():
            n += 1
        return f"{stem}_v{n}"


def create(ws: Path, files: list[Path], name: str | None = None, move: bool = False) -> Project:
    """A new project. With no files a name is required (e.g. to analyse a reference video first)."""
    if not files and not name:
        raise NveError("Give the video/photo files, or a --name for an empty project.")
    files = [Path(f).expanduser().resolve() for f in files]
    for f in files:
        if not f.exists():
            raise NveError(f"File not found: {f}")
        if f.suffix.lower() not in VIDEO_EXT | IMAGE_EXT | AUDIO_EXT:
            raise NveError(f"Unsupported file type: {f.name}")
    date = dt.date.today().isoformat()
    slug = f"{date}-{slugify(name or files[0].stem)}"
    path = ws / "projects" / slug
    i = 2
    while path.exists():
        path = ws / "projects" / f"{slug}-{i}"
        i += 1
    for d in SUBDIRS:
        (path / d).mkdir(parents=True, exist_ok=True)
    sources = []
    for idx, f in enumerate(files):
        sid = chr(ord("a") + idx) if idx < 26 else f"s{idx}"
        dest = path / "source" / f.name
        (shutil.move if move else shutil.copy2)(f, dest)
        sources.append({"id": sid, "path": f"source/{f.name}"})
    dump_json(path / "project.json", {"schema": "nve.project/1", "created": dt.datetime.now().isoformat(timespec="seconds"),
                                      "name": name or files[0].stem, "sources": sources})
    (path / "project.md").write_text(f"# {name or files[0].stem}\n\nnve project, created {date}.\n", encoding="utf-8")
    log(f"project created: {path}")
    return Project(path)


def add_reference(prj: Project, files: list[Path]) -> list[str]:
    out = []
    for f in files:
        f = Path(f).expanduser().resolve()
        dest = prj.p("reference", f.name)
        shutil.copy2(f, dest)
        out.append(f"reference/{f.name}")
    return out
