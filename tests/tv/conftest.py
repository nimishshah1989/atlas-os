"""TV test suite conftest.

Sets ATLAS_AUTH_DISABLED before any atlas module is imported so that
JWTAuthMiddleware runs in bypass mode for all tests in this directory.
Must be evaluated before test_*.py files import atlas.api.
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")
