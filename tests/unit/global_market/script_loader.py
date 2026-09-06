"""Load a ``scripts/global_market/<name>.py`` script as a module for tests.

The scripts run as FILES in the orchestrators (``python scripts/global_market/x.py``), so
their basenames were never meant to be importable — and some collide with India's
(``scripts/foundation/ingest_macro.py`` vs ``scripts/global_market/ingest_macro.py``; ``_gdb``
puts ``scripts/foundation`` first on ``sys.path``). Loading by path under a unique module
name sidesteps the collision; the module is registered in ``sys.modules`` because the
scripts' dataclasses resolve their (string) annotations through it.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "global_market"

# The SPY calendar the guard and snapshot tests share: Tue 2026-09-01 … Fri 09-04 (Mon 09-07 is
# Labor Day: no session), then Tue 09-08. Calendar facts, not market data (rule #0).
LABOR_DAY_WEEK = [
    dt.date(2026, 9, 1),
    dt.date(2026, 9, 2),
    dt.date(2026, 9, 3),
    dt.date(2026, 9, 4),
    dt.date(2026, 9, 8),
]


def load_global_script(name: str) -> ModuleType:
    """The module at ``scripts/global_market/<name>.py``, e.g. ``"ingest_macro"``."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))  # the scripts do `import _gdb` (a sibling)
    module_name = f"global_market_script_{name}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"no script {name}.py under {SCRIPTS_DIR}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod
