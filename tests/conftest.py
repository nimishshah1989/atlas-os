"""Root test conftest: pre-load heavy native dependencies.

vectorbt requires real numba and requests (not stubs). This root conftest loads
both packages before any subdirectory conftest can insert lightweight stubs.

tests/unit/conftest.py stubs numba for pandas_ta in CI environments without JIT.
tests/scripts/conftest.py stubs requests to avoid macOS SSL keychain hangs.
These stubs break vectorbt, which uses both packages in its import chain.

Loading the real packages here (root conftest runs before subdirectory conftests)
ensures sys.modules["numba"] and sys.modules["requests"] are real before stubs
check 'if "X" not in sys.modules'.
"""

from __future__ import annotations

import importlib.util

# Pre-load numba and requests only if they are installed.
# This prevents subdirectory conftests from stubbing packages vectorbt needs.
if importlib.util.find_spec("numba") is not None:
    import numba  # noqa: F401

if importlib.util.find_spec("requests") is not None:
    import requests  # noqa: F401
