#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block writes into the nve install folder.

User customisations and code Claude writes for the user belong in <workspace>/custom/ or
projects/<p>/work/scripts/. Exit code 2 blocks the tool call and shows the message to Claude.
Set NVE_DEV=1 to allow edits (maintainers working on nve itself).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1]).resolve()
MSG = (f"nve: do not write into the nve install folder ({ROOT}). Put user templates/blocks/scripts in "
       "<workspace>/custom/ (reusable code: custom/scripts/<name>/) or projects/<p>/work/scripts/ (one-off).")


def inside(p: str) -> bool:
    try:
        Path(p).expanduser().resolve().relative_to(ROOT)
        return True
    except (ValueError, OSError):
        return False


def main() -> None:
    if os.environ.get("NVE_DEV") == "1":
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool, ti = data.get("tool_name", ""), data.get("tool_input", {}) or {}
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        if target and inside(target):
            print(MSG, file=sys.stderr)
            sys.exit(2)
    elif tool == "Bash":
        cmd = ti.get("command", "")
        root = str(ROOT)
        if root in cmd and re.search(r"(>|\btee\b|\bcp\b|\bmv\b|\brm\b|\bsed\s+-i|\btouch\b|\bmkdir\b|\bln\b)", cmd):
            # allow read-only use and running the CLI itself
            writes_into = re.search(r"(>{1,2}|\btee\b|\bcp\b.*|\bmv\b.*|\btouch\b|\bmkdir\b|\bln\b.*)\s*['\"]?" + re.escape(root), cmd)
            if writes_into or re.search(r"\b(rm|sed\s+-i)\b[^|;&]*" + re.escape(root), cmd):
                print(MSG, file=sys.stderr)
                sys.exit(2)


if __name__ == "__main__":
    main()
