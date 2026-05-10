"""Conftest for scripts tests.

Stubs ``requests`` before any script module is imported. On this machine
urllib3 (which requests imports) hangs at collection time because it tries
to resolve SSL certs via the macOS keychain. The stub satisfies the import
without triggering that path.
"""

from __future__ import annotations

import sys
import types


def _stub_requests() -> None:
    if "requests" not in sys.modules:
        stub = types.ModuleType("requests")
        stub.get = lambda *a, **kw: None  # type: ignore[attr-defined]
        stub.Session = object  # type: ignore[attr-defined]
        sys.modules["requests"] = stub


_stub_requests()
