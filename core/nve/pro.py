"""Bridge to the Pro features in <install>/pro/python/nve_pro (the public editions do not ship pro/)."""
from __future__ import annotations

import importlib
import sys

from nve.paths import PRO_ROOT, NveError

# Editions without these features stay silent about them: the commands are not registered, and this message is
# only for Claude (do not pass it on to the user).
PRO_ONLY = "{what} is not available here. Do not mention it to the user; work by hand (references/analyze.md)."


def available() -> bool:
    return (PRO_ROOT / "python" / "nve_pro").is_dir()


def load(module: str, what: str = "This feature"):
    if not available():
        raise NveError(PRO_ONLY.format(what=what))
    p = str(PRO_ROOT / "python")
    if p not in sys.path:
        sys.path.insert(0, p)
    return importlib.import_module(f"nve_pro.{module}")
