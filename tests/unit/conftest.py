"""Unit-test conftest: stub heavy native dependencies before any import."""

from __future__ import annotations

import sys
import types


def _stub_numba() -> None:
    """Insert a minimal numba stub so pandas_ta can be imported without the JIT compiler.

    pandas_ta._math does `from numba import njit`; we provide a no-op decorator.
    This is only needed when numba is absent from the venv (CI, lightweight dev).
    """
    # Guard: only stub if numba is genuinely absent from the venv.
    # If it's installed but not yet imported, importing it here is safer than stubbing.
    try:
        import importlib.util

        if importlib.util.find_spec("numba") is not None:
            return  # real numba is installed — don't stub it
    except Exception:
        pass
    if "numba" not in sys.modules:
        numba_stub = types.ModuleType("numba")

        def _njit(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
            def _decorator(fn):  # type: ignore[no-untyped-def]
                return fn

            # Called as @njit directly (no args) — first arg is the function
            if len(_args) == 1 and callable(_args[0]) and not _kwargs:
                return _args[0]
            return _decorator

        numba_stub.njit = _njit  # type: ignore[attr-defined]
        sys.modules["numba"] = numba_stub


_stub_numba()
