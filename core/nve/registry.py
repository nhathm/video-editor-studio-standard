"""Layered registry: core < pro < user < project.

Every template, block and style preset has a namespaced id:
    core:<name>  shipped in INSTALL_ROOT/<kind>s/core/<name>/   (read-only)
    pro:<name>   shipped in INSTALL_ROOT/pro/<kind>s/<name>/    (read-only, Pro edition only)
    user:<name>  the user's own, in WORKSPACE/custom/<kind>s/<name>/

A user item can never claim the core: or pro: namespace, so it can never shadow a shipped one.
To customise, a user item `extends` another id and applies a `patch` of dotted keys:

    {"id": "user:my-th", "extends": "core:talking-head@^1",
     "patch": {"style.font.title": "Be Vietnam Pro", "captions.group_words": 4}}
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nve.paths import INSTALL_ROOT, PRO_ROOT, NveError
from nve.util import load_data

KINDS = {"template": "template", "block": "block"}
MANIFEST = {"template": ("template.json", "template.yaml"), "block": ("block.json", "block.yaml")}
SHIPPED_NS = ("core", "pro")


@dataclass
class Item:
    id: str
    kind: str
    path: Path          # folder holding the manifest
    data: dict[str, Any]


def _ns(item_id: str) -> tuple[str, str, str | None]:
    m = re.fullmatch(r"(core|pro|user):([a-z0-9][a-z0-9._-]*)(?:@(\^?\d+(?:\.\d+)*))?", item_id)
    if not m:
        raise NveError(f"Bad id '{item_id}': expected core:<name>, pro:<name> or user:<name> (lowercase).")
    return m.group(1), m.group(2), m.group(3)


def _roots(kind: str, workspace: Path | None, edition: dict | None) -> list[tuple[str, Path]]:
    plural = kind + "s"
    roots = [("core", INSTALL_ROOT / plural / "core")]
    if edition is None or edition.get("tier") == "pro":
        roots.append(("pro", PRO_ROOT / plural))
    if workspace:
        roots.append(("user", workspace / "custom" / plural))
    return roots


def _read_manifest(folder: Path, kind: str) -> dict | None:
    for name in MANIFEST[kind]:
        f = folder / name
        if f.exists():
            return load_data(f) or {}
    return None


def scan(kind: str, workspace: Path | None = None, edition: dict | None = None) -> dict[str, Item]:
    found: dict[str, Item] = {}
    for ns, root in _roots(kind, workspace, edition):
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            data = _read_manifest(folder, kind)
            if data is None:
                continue
            declared = data.get("id")
            item_id = f"{ns}:{folder.name}"
            if declared and declared != item_id:
                dns = declared.split(":", 1)[0]
                if ns == "user" and dns in SHIPPED_NS:
                    raise NveError(f"{folder} declares id '{declared}', but user items cannot use the '{dns}:' "
                                   f"namespace (that would override a shipped {kind}). Rename it to 'user:{folder.name}' "
                                   f"and use \"extends\": \"{declared}\" instead.")
                raise NveError(f"{folder}: id '{declared}' does not match its folder; expected '{item_id}'.")
            found[item_id] = Item(item_id, kind, folder, data)
    return found


def set_dotted(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = cur[k] = {}
        cur = nxt
    cur[keys[-1]] = value


def deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _major(version: str | None) -> int | None:
    return int(str(version).split(".")[0]) if version else None


def resolve(item_id: str, kind: str, workspace: Path | None = None, edition: dict | None = None,
            _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return the fully merged data for an id, following `extends` chains."""
    ns, name, want = _ns(item_id)
    bare = f"{ns}:{name}"
    if bare in _seen:
        raise NveError(f"{kind} extends loop: {' -> '.join(_seen + (bare,))}")
    items = scan(kind, workspace, edition)
    if bare not in items:
        avail = ", ".join(sorted(items)) or "none"
        raise NveError(f"Unknown {kind} '{bare}'. Available: {avail}")
    it = items[bare]
    data = copy.deepcopy(it.data)
    if want:
        have_major, want_major = _major(data.get("version", "1")), _major(want.lstrip("^"))
        if have_major != want_major:
            raise NveError(f"{bare} is version {data.get('version')}, but {want} was requested. "
                           f"Update the extends line after checking the changelog.")
    parent = data.pop("extends", None)
    patch = data.pop("patch", {}) or {}
    chain = [bare]
    if parent:
        base = resolve(parent, kind, workspace, edition, _seen + (bare,))
        base.pop("_path", None)
        chain += base.pop("_chain", [])
        data = deep_merge(base, data)
    for k, v in patch.items():
        set_dotted(data, k, v)
    data["id"] = bare
    data["_path"] = str(it.path)
    data["_chain"] = chain
    return data


def fork(item_id: str, kind: str, new_name: str, workspace: Path) -> Path:
    """Create custom/<kind>s/<new_name>/ that extends item_id (never copies over a shipped file)."""
    ns, name, _ = _ns(item_id)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", new_name):
        raise NveError("New name must be lowercase letters, digits, '-', '_' or '.'.")
    dest = workspace / "custom" / (kind + "s") / new_name
    if dest.exists():
        raise NveError(f"{dest} already exists.")
    resolve(item_id, kind, workspace)  # validate it exists
    dest.mkdir(parents=True)
    from nve.util import dump_json
    dump_json(dest / MANIFEST[kind][0], {"id": f"user:{new_name}", "extends": f"{ns}:{name}", "patch": {}})
    return dest
