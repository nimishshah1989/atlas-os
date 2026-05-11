#!/usr/bin/env python3
"""Pre-commit hook: enforce bounded-context import boundaries.

Each top-level package under atlas/ is a bounded context. They MUST NOT
reach into each other's internals. Allowed exchange happens through:
  - The package's __init__.py public exports
  - The shared kernel (atlas/primitives/, atlas/db.py)

This stops the modulith from quietly turning into a tangle of cross-cutting
imports. The day you outgrow it and need to extract a context into its own
service, the boundaries are already crisp.

Reads staged Python files, parses imports, fails on forbidden combinations.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# Bounded contexts under atlas/. Each may import:
#   - itself
#   - the shared kernel (primitives, db, config)
# Adjust as new contexts appear.
CONTEXTS: tuple[str, ...] = (
    "atlas.compute",
    "atlas.health",
    "atlas.universe",
    "atlas.validation",
    "atlas.simulation",
    "atlas.api",
    # Phase 2: validator agent — read-only DB access via shared kernel only
    "atlas.agents",
)

SHARED_KERNEL: tuple[str, ...] = (
    "atlas.primitives",
    "atlas.db",
    "atlas.config",
    "atlas.preflight",  # one-off; fine to import from
)

# Direction rules: which contexts may depend on which.
# Default: NO context may import another context's internals.
ALLOWED_EDGES: set[tuple[str, str]] = {
    # simulation → compute: simulation uses open_compute_session / bulk_upsert from
    # compute._session. Both contexts share the same Postgres schema and connection
    # pool. Extracting the session manager into the shared kernel (atlas.db) is the
    # long-term fix; for now this explicit edge makes the dependency visible.
    ("atlas.simulation", "atlas.compute"),
    # api → simulation: the API surface for custom portfolios (M7 Phase 3) is a
    # thin HTTP wrapper over atlas.simulation.custom orchestrators (validate,
    # save, trigger background backtest). The simulation context owns the
    # business logic; api owns the request/response shape.
    ("atlas.api", "atlas.simulation"),
    # api → compute: api endpoints read from atlas tables via the same
    # open_compute_session helper used everywhere else (statement_timeout=0
    # reset on the pooled connection). Same long-term fix as above — promote
    # session manager into atlas.db.
    ("atlas.api", "atlas.compute"),
    # health → compute: atlas.health.runs uses open_compute_session to write
    # pipeline run rows with statement_timeout=0 (avoids Supabase pooler
    # timeout on run-log inserts). Pre-existing edge; documented here so
    # staged edits to runs.py don't trip the boundary check.
    ("atlas.health", "atlas.compute"),
    # validation → compute: tier2_metrics.py and tier3_states.py call
    # open_compute_session to read from atlas tables for hand-validation
    # spot-checks. Pre-existing edge (present before 2026-05 health audit).
    # Long-term fix: extract session factory into atlas.db shared kernel.
    ("atlas.validation", "atlas.compute"),
}


def staged_python_files() -> list[Path]:
    out = subprocess.check_output(  # noqa: S603
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],  # noqa: S607
        text=True,
    )
    paths = [Path(line.strip()) for line in out.splitlines() if line.strip()]
    return [p for p in paths if p.suffix == ".py" and str(p).startswith("atlas/")]


def context_of(module: str) -> str | None:
    for ctx in CONTEXTS:
        if module == ctx or module.startswith(ctx + "."):
            return ctx
    return None


def is_kernel(module: str) -> bool:
    return any(module == k or module.startswith(k + ".") for k in SHARED_KERNEL)


def imports_in(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
    return out


def context_of_path(path: Path) -> str | None:
    parts = path.parts
    if len(parts) < 2 or parts[0] != "atlas":
        return None
    return f"atlas.{parts[1]}"


def main() -> int:
    failures: list[str] = []
    for f in staged_python_files():
        my_ctx = context_of_path(f)
        if my_ctx not in CONTEXTS:
            continue
        for imp in imports_in(f):
            if not imp.startswith("atlas."):
                continue
            if is_kernel(imp):
                continue
            other_ctx = context_of(imp)
            if other_ctx is None or other_ctx == my_ctx:
                continue
            if (my_ctx, other_ctx) in ALLOWED_EDGES:
                continue
            failures.append(f"{f}: {my_ctx} → {other_ctx} (forbidden) — `{imp}`")

    if failures:
        print("✗ Forbidden cross-context imports:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRule: each top-level package under atlas/ is a bounded context.\n"
            "Cross-context imports go through the shared kernel\n"
            "(atlas/primitives, atlas/db, atlas/config) or through the public\n"
            "__init__.py of the target context. If you need a new edge,\n"
            "add it to ALLOWED_EDGES in scripts/hooks/check_module_boundaries.py\n"
            "and document why in a commit message.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
