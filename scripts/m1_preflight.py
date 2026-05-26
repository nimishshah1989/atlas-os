#!/usr/bin/env python3
"""Convenience wrapper — run the pre-flight check from scripts/.

Equivalent to ``python -m atlas.preflight``. Lets you invoke without the
``-m`` flag, and mirrors the existing ``scripts/m1_run.py`` convention.
"""

import sys

from atlas.preflight import main

if __name__ == "__main__":
    sys.exit(main())
