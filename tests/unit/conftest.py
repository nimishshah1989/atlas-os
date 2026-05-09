"""Unit-test conftest: stub heavy native dependencies before any import."""

from __future__ import annotations

import sys
import types


def _stub_numba() -> None:
    """Insert a minimal numba stub so pandas_ta can be imported without the JIT compiler.

    pandas_ta._math does `from numba import njit`; we provide a no-op decorator.
    This is only needed when numba is absent from the venv (CI, lightweight dev).
    """
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
