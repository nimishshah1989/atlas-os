"""Trading test conftest: pre-load real numba before tests/unit/conftest.py stubs it.

tests/unit/conftest.py inserts a minimal numba stub to support pandas_ta imports
without the JIT compiler. When tests/unit/ and tests/trading/ run in the same
pytest session, the stub is inserted before simulator tests run, which breaks
vectorbt (which needs numba.core). Loading real numba here ensures it is already
in sys.modules when the unit conftest runs its guard.
"""

from __future__ import annotations

import numba  # noqa: F401 — side-effect import: registers real numba in sys.modules
