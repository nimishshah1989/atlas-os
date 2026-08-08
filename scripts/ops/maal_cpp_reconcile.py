#!/usr/bin/env python3
"""Prove every MaaL figure Atlas displays still equals what CPP says it is.

A 4,975.1% return sat on a client page and nothing objected. This is the thing that
objects. It runs nightly inside atlas_daily, reads BOTH databases, and fails the run
on any disagreement beyond display rounding.

It checks four things, in the order they can go wrong:

  1. THE MIRROR — every field in COPIED_FIELDS, CPP's row against Atlas's copy.
  2. THE READ — what the board actually renders. Runs /portfolios' own since-inception
     expression against the real registrations, so a page that quietly reverts to
     nav/initial_capital fails here rather than on a client's screen.
  3. THE AGE RULE — a book under a year old must serve no XIRR and no CAGR. IND11 at
     three months reports an XIRR of -94.51%.
  4. THE MARKS — the newest position snapshot is priced by CPP, and the NAV history is
     whole rather than the single newest point.

Needs MAAL_SOURCE_DB_URL (box only). Read-only against both databases.

    python scripts/ops/maal_cpp_reconcile.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation"))
import _db  # pyright: ignore[reportMissingImports]

from atlas.maal.cpp_metrics import COPIED_FIELDS, annualised_allowed, mismatches
from atlas.maal.source import CODE_BY_CLIENT_CODE

M = "atlas_foundation"

# Generous, like the sync's: this is ~10 rows of arithmetic, so anything past a minute
# means CPP is wedged and a hung gate is worse than a failed one.
_CONNECT_TIMEOUT_S = 15
_STATEMENT_TIMEOUT_MS = 60_000

# Below this, a nav_date gap is CPP not having computed that day. Above it, Atlas is
# holding a figure CPP has since moved on from, and the board is quoting stale money.
_MAX_STALENESS_DAYS = 7


def _atlas(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read through SQLAlchemy, not read_df: pandas turns numeric into float and NULL
    into NaN, and this gate exists precisely to notice the difference."""
    with _db.engine().connect() as conn:
        return [dict(m) for m in conn.execute(text(sql), params or {}).mappings()]


def _cpp(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    url = os.environ.get("MAAL_SOURCE_DB_URL", "").strip()
    if not url:
        raise SystemExit("MAAL_SOURCE_DB_URL is not set — see docs/maal-process.md")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": _CONNECT_TIMEOUT_S,
            "options": f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}",
        },
    )
    with engine.connect() as conn:
        return [dict(m) for m in conn.execute(text(sql), params).mappings()]


def _check_mirror(problems: list[str]) -> None:
    codes = list(CODE_BY_CLIENT_CODE)
    fields = ", ".join("r." + f for f in COPIED_FIELDS)
    truth = {
        CODE_BY_CLIENT_CODE[r["client_code"]]: r
        for r in _cpp(
            f"""
            SELECT DISTINCT ON (p.client_code) p.client_code, r.computed_date, {fields}
            FROM cpp_risk_metrics r JOIN cpp_portfolios p ON p.id = r.portfolio_id
            WHERE p.client_code = ANY(:codes)
            ORDER BY p.client_code, r.computed_date DESC
            """,
            {"codes": codes},
        )
    }
    copied = {
        r["maal_code"]: r
        for r in _atlas(f"""
            SELECT DISTINCT ON (maal_code) * FROM {M}.maal_cpp_metrics
            ORDER BY maal_code, computed_date DESC
        """)
    }

    for code in sorted(CODE_BY_CLIENT_CODE.values()):
        if code not in truth:
            problems.append(f"{code}: CPP has no risk-metrics row at all")
            continue
        if code not in copied:
            problems.append(f"{code}: never synced — the board would show no return")
            continue
        cpp_row, atlas_row = truth[code], copied[code]
        if cpp_row["computed_date"] != atlas_row["computed_date"]:
            lag = (cpp_row["computed_date"] - atlas_row["computed_date"]).days
            # Not a mismatch to compare across — say so and move on, rather than
            # reporting eighteen field differences that are really one stale sync.
            problems.append(
                f"{code}: Atlas holds {atlas_row['computed_date']}, CPP has moved to "
                f"{cpp_row['computed_date']} ({lag}d stale) — the sync has not run"
            )
            continue
        for m in mismatches(cpp_row, atlas_row):
            problems.append(f"{code}: {m}")
        print(
            f"    {code:8s} computed={cpp_row['computed_date']} "
            f"since_inception={cpp_row['absolute_return']}%"
        )


def _check_what_the_board_renders(problems: list[str]) -> None:
    """/portfolios' own expression, run against the real registrations."""
    rows = _atlas(f"""
        SELECT m.params->>'maal_code' AS maal_code, m.initial_capital, ln.nav,
               cm.absolute_return, cm.age_days, cm.cagr, cm.xirr,
               cm.return_1m, cm.return_3m, cm.return_6m,
               CASE WHEN m.params->>'source' = 'cpp' THEN cm.absolute_return
                    ELSE (ln.nav / nullif(m.initial_capital, 0) - 1) * 100
               END AS since_inception_pct
        FROM {M}.portfolio_master m
        LEFT JOIN {M}.maal_book_metrics cm ON cm.maal_code = m.params->>'maal_code'
        LEFT JOIN LATERAL (
          SELECT nav FROM {M}.portfolio_nav_daily n
          WHERE n.portfolio_id = m.portfolio_id AND n.run_type = 'live'
          ORDER BY date DESC LIMIT 1
        ) ln ON true
        WHERE m.params->>'source' = 'cpp'
    """)
    if len(rows) != 3:
        problems.append(f"expected 3 registered CPP books, found {len(rows)}")

    for r in rows:
        code = r["maal_code"]
        if r["since_inception_pct"] != r["absolute_return"]:
            problems.append(
                f"{code}: the board would render {r['since_inception_pct']}% since "
                f"inception, CPP says {r['absolute_return']}% — a derived figure is back"
            )
        if r["nav"] is not None and r["initial_capital"]:
            placeholder = (r["nav"] / r["initial_capital"] - 1) * 100
            if (
                r["since_inception_pct"] is not None
                and abs(r["since_inception_pct"] - placeholder) < 1
            ):
                problems.append(
                    f"{code}: the rendered return tracks nav/initial_capital "
                    f"({placeholder:.1f}%) — the placeholder corpus is being divided by again"
                )

        # The FM's rule, checked on what is SERVED rather than on what is stored.
        if annualised_allowed(r["age_days"]):
            continue
        for figure in ("xirr", "cagr"):
            if r[figure] is not None:
                problems.append(
                    f"{code} is {r['age_days']} days old and serves a {figure.upper()} of "
                    f"{r[figure]}% — an annualisation artefact is reaching clients"
                )
        if all(r[f] is None for f in ("return_1m", "return_3m", "return_6m")):
            problems.append(
                f"{code}: annualised figures withheld and no period return offered instead"
            )


def _check_marks_and_history(problems: list[str]) -> None:
    codes = list(CODE_BY_CLIENT_CODE)
    cpp_navs = {
        CODE_BY_CLIENT_CODE[r["client_code"]]: r
        for r in _cpp(
            """
            SELECT p.client_code, count(*) AS points, max(n.nav_date) AS last
            FROM cpp_nav_series n JOIN cpp_portfolios p ON p.id = n.portfolio_id
            WHERE p.client_code = ANY(:codes) GROUP BY p.client_code
            """,
            {"codes": codes},
        )
    }
    ours = {
        r["maal_code"]: r
        for r in _atlas(f"""
            SELECT maal_code, count(*) AS points, max(nav_date) AS last
            FROM {M}.maal_cpp_nav GROUP BY maal_code
        """)
    }
    for code, src in sorted(cpp_navs.items()):
        mine = ours.get(code)
        if mine is None:
            problems.append(f"{code}: no NAV history mirrored at all")
            continue
        if mine["points"] != src["points"]:
            problems.append(
                f"{code}: {mine['points']} NAV points mirrored against CPP's "
                f"{src['points']} — the chart is missing {src['points'] - mine['points']} days"
            )
        stale = (src["last"] - mine["last"]).days
        if stale > _MAX_STALENESS_DAYS:
            problems.append(f"{code}: NAV mirror is {stale}d behind CPP ({mine['last']})")

    # A day's snapshot is ONE complete look at the book. Two CPP dates under a single
    # as_of means a name sold between the noon and 22:00 runs is still in the book the
    # desk places sells from.
    for r in _atlas(f"""
        SELECT as_of, maal_code, count(DISTINCT source_as_of) AS views
        FROM {M}.maal_holding_snapshot
        GROUP BY as_of, maal_code HAVING count(DISTINCT source_as_of) > 1
    """):
        problems.append(
            f"{r['maal_code']}: the {r['as_of']} snapshot mixes {r['views']} different CPP "
            f"dates — it is holding positions CPP has already dropped"
        )

    # Every position in the newest snapshot must carry CPP's own mark. An Atlas close
    # here means the book is valued by a source that cannot agree with the statement.
    for r in _atlas(f"""
        SELECT s.maal_code, count(*) FILTER (WHERE s.cpp_value IS NULL) AS unpriced
        FROM {M}.maal_holding_snapshot s
        JOIN (SELECT maal_code AS c, max(as_of) AS a FROM {M}.maal_holding_snapshot
              GROUP BY maal_code) l ON l.c = s.maal_code AND l.a = s.as_of
        GROUP BY s.maal_code
    """):
        if r["unpriced"]:
            problems.append(
                f"{r['maal_code']}: {r['unpriced']} position(s) in the newest snapshot have "
                f"no CPP mark and fall back to Atlas's NSE close"
            )


def main() -> int:
    problems: list[str] = []
    _check_mirror(problems)
    _check_what_the_board_renders(problems)
    _check_marks_and_history(problems)

    if problems:
        print(f"[maal_cpp_reconcile] FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("[maal_cpp_reconcile] PASS — every displayed MaaL figure matches CPP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
