"""Client 360 ("the Kundli"): per-client parametrized rollups of every book
exhibit above, for Task 6's client detail page. Header + timeline + funds
table + label check + sector look-through live here; overlap/fees/cut-list
and behaviour/what-ifs slices live in the sibling data_client360_behaviour.py
to stay under the 600-LOC file limit. Same contract as every other module:
real query output only.
"""

from __future__ import annotations

from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, nav_series

from .data import _f, lcr_py

# Confirmed via information_schema: the only 4 distinct kinds actually
# written by build_equity_curves.py — never hardcode a 5th.
CURVE_EVENT_KINDS = ("panic_sell", "big_inflow", "big_outflow", "sip_stop")

# build_equity_curves.py "just records the number"; the <70% -> "insufficient"
# rule is build_capability_app.py's OWN app-level convention (grepped from its
# svgStoryCurve()), reused verbatim here rather than invented fresh.
COVERAGE_INSUFFICIENT_PCT = 70.0


def crisis_windows_once(conn) -> list[dict]:
    """Book-wide drawdown windows, computed ONCE and shared across every
    client-360 page (constraint 15: never hardcoded, but also never
    recomputed per client — the window list doesn't depend on client_id)."""
    bench = nav_series(conn, BENCH_ID)
    windows = drawdown_windows(bench)
    return [
        {"start": str(a.date()), "end": str(b.date()), "still_open": b == bench.index[-1]}
        for a, b in windows
    ]


def client_header(conn, client_id: int) -> dict:
    """Header strip: name, family group, tenure, put-in/taken-out/worth-now,
    "grew at N%/year" (from client_benchmark's exact cashflow-matched XIRR,
    never called XIRR/alpha in UI text), segment chip."""
    cur = conn.cursor()
    cur.execute(
        "select full_name, family_group from wealth.clients where client_id = %s", (client_id,)
    )
    row = cur.fetchone()
    name, family = row if row else (None, None)

    cur.execute(
        """select xirr_client::float, first_flow, gross_in::float, gross_out::float,
                  terminal_mv::float, approx
           from wealth.client_benchmark where client_id = %s""",
        (client_id,),
    )
    bm = cur.fetchone()

    cur.execute(
        "select segment, reason from wealth.client_segments where client_id = %s", (client_id,)
    )
    seg = cur.fetchone()

    xirr = bm[0] if bm else None
    if bm is None or xirr is None:
        return {
            "client_id": client_id,
            "name": name,
            "family_group": family,
            "insufficient": True,
            "message": (
                "no flow-complete benchmark comparison for this client "
                "(no client_benchmark row, or the growth figure isn't computable)"
            ),
            "segment": seg[0] if seg else None,
            "working": {
                "inputs": [],
                "rule": "wealth.client_benchmark has no usable row for this client_id",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    xirr, first_flow, gross_in, gross_out, terminal_mv, approx = bm
    since_year = first_flow.year if first_flow else None
    verdict = (
        f"with the firm since {since_year}; put in {lcr_py(gross_in)}, took out "
        f"{lcr_py(gross_out)}, worth {lcr_py(terminal_mv)} today; grew at {xirr:+.2f}%/year."
    )

    return {
        "client_id": client_id,
        "name": name,
        "family_group": family,
        "since_year": since_year,
        "gross_in_rs": _f(gross_in),
        "gross_out_rs": _f(gross_out),
        "worth_now_rs": _f(terminal_mv),
        "grew_pct_per_year": _f(xirr),
        "approx": bool(approx),
        "segment": seg[0] if seg else None,
        "segment_reason": seg[1] if seg else None,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "First real cash flow", "value": str(first_flow)},
                {"label": "Gross in", "value": _f(gross_in)},
                {"label": "Gross out", "value": _f(gross_out)},
                {"label": "Worth now", "value": _f(terminal_mv)},
                {"label": "Grew at %/year", "value": _f(xirr)},
            ],
            "rule": (
                "wealth.client_benchmark (exact_benchmark.py): cashflow-matched annualized "
                "growth rate on the client's own real external cash flows (Folio Ledgers) "
                "from first_flow to today, terminal value at today's NAV. approx=True flags "
                "clients with opening-balance/transfer-in units that have no cash-flow "
                "history behind part of the book."
            ),
            "assumptions": (
                [
                    {
                        "text": "this client's book includes opening-balance or transfer-in "
                        "units with no real flow history — the growth figure is not a full "
                        "replay",
                        "bias": "estimate — part of the return figure rests on an assumed "
                        "entry point, not a real dated flow",
                    }
                ]
                if approx
                else []
            ),
            "steps": [{"label": "Rows for this client", "value": 1}],
            "sample_rows": [
                {
                    "client_id": client_id,
                    "grew_pct_per_year": _f(xirr),
                    "worth_now_rs": _f(terminal_mv),
                }
            ],
            "sample_of": 1,
            "honesty": "exact",
        },
    }


def client_timeline(conn, client_id: int, crisis_windows: list[dict]) -> dict:
    """Timeline: monthly value_rs + cumulative net-invested line from
    wealth.client_curves, event markers from wealth.client_curve_events,
    crisis windows shaded (shared book-wide list, not recomputed). The <70%
    coverage rule is reused verbatim from build_capability_app.py's own
    convention — not a new threshold."""
    cur = conn.cursor()
    cur.execute(
        """select month, value_rs::float, net_flow_rs::float, coverage_pct::float
           from wealth.client_curves where client_id = %s order by month""",
        (client_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "not enough NAV history in mapped funds to trace this client's value over time",
            "working": {
                "inputs": [],
                "rule": "wealth.client_curves has no rows for this client_id",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    # build_capability_app.py's own convention: the first month's coverage_pct
    # represents the client (distinct on client_id order by month) — reused
    # verbatim rather than picking latest/average.
    coverage_pct = rows[0][3]
    insufficient = coverage_pct is not None and coverage_pct < COVERAGE_INSUFFICIENT_PCT
    cumulative_net_flow = []
    running = 0.0
    for _m, _v, nf, _c in rows:
        running += nf or 0.0
        cumulative_net_flow.append(_f(running))

    cur.execute(
        """select event_date, kind, amount_rs::float
           from wealth.client_curve_events where client_id = %s order by event_date""",
        (client_id,),
    )
    ev_rows = cur.fetchall()

    verdict = (
        f"{len(rows)} months tracked, coverage {coverage_pct:.0f}% "
        f"({'insufficient — below the 70% threshold' if insufficient else 'sufficient'}); "
        f"{len(ev_rows)} flagged events."
    )

    return {
        "client_id": client_id,
        "months": [d.strftime("%Y-%m") for d, *_ in rows],
        "values_rs": [_f(v) for _m, v, _nf, _c in rows],
        "cumulative_net_flow_rs": cumulative_net_flow,
        "coverage_pct": _f(coverage_pct),
        "insufficient": insufficient,
        "events": [
            {"date": str(d), "kind": k, "amount_rs": _f(amt)}
            for d, k, amt in ev_rows
            if k in CURVE_EVENT_KINDS
        ],
        "crisis_windows": crisis_windows,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Months tracked", "value": len(rows)},
                {"label": "Coverage pct (first month)", "value": _f(coverage_pct)},
                {"label": "Events", "value": len(ev_rows)},
            ],
            "rule": (
                "wealth.client_curves: monthly value = units held (from real transactions) x "
                "month-end NAV; coverage_pct = share of currently-held schemes with mapped NAV "
                "history (build_equity_curves.py 'just records the number' per its own "
                "docstring). The <70% -> insufficient rule and wording is build_capability_app.py's "
                "own app-level convention, not something the engine itself asserts — reused "
                "verbatim, not a new threshold. Events are real transaction-dated flags: "
                f"{', '.join(CURVE_EVENT_KINDS)} (confirmed via select distinct kind)."
            ),
            "assumptions": (
                [
                    {
                        "text": "this client's curve has coverage_pct below 70% — the value "
                        "series may be missing NAV history for part of the holdings",
                        "bias": "estimate — below-threshold months should be read as "
                        "directional, not a precise value",
                    }
                ]
                if insufficient
                else []
            ),
            "steps": [{"label": "Months returned", "value": len(rows)}],
            "sample_rows": [
                {"month": d.strftime("%Y-%m"), "value_rs": _f(v)} for d, v, _nf, _c in rows[:20]
            ],
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }


def client_sector_lookthrough(conn, client_id: int) -> dict:
    """Sector look-through: client_stock_exposure bucketed + sector-mapped
    via instrument_master. Coverage computed FRESH per client (book-wide is
    ~67% per spec, never hardcoded on a client page)."""
    cur = conn.cursor()
    cur.execute(
        """select cse.bucket, im.sector, cse.exposure::float
           from wealth.client_stock_exposure cse
           left join atlas_foundation.instrument_master im using (instrument_id)
           where cse.client_id = %s""",
        (client_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "no look-through holdings mapped for this client",
            "working": {
                "inputs": [],
                "rule": "wealth.client_stock_exposure has no rows for this client_id",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    total = sum(e for _b, _s, e in rows)
    by_bucket: dict[str, float] = {}
    by_sector: dict[str, float] = {}
    for bucket, sector, exposure in rows:
        by_bucket[bucket] = by_bucket.get(bucket, 0.0) + exposure
        if bucket == "atlas_scored_stock" and sector:
            by_sector[sector] = by_sector.get(sector, 0.0) + exposure

    identified = by_bucket.get("atlas_scored_stock", 0.0)
    identified_pct = _f(100.0 * identified / total) if total else None

    verdict = (
        f"sector identified {identified_pct:.1f}% of look-through value; rest: "
        + ", ".join(
            f"{b} {_f(100.0 * v / total):.1f}%"
            for b, v in by_bucket.items()
            if b != "atlas_scored_stock"
        )
        if total
        else "no look-through value for this client."
    )

    return {
        "client_id": client_id,
        "total_exposure_rs": _f(total),
        "identified_pct": identified_pct,
        "bucket_pct": {b: _f(100.0 * v / total) if total else None for b, v in by_bucket.items()},
        "sector_pct": {
            s: _f(100.0 * v / total) if total else None
            for s, v in sorted(by_sector.items(), key=lambda kv: -kv[1])
        },
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Total look-through exposure", "value": _f(total)},
                {"label": "Sector-identified pct", "value": identified_pct},
                {"label": "Buckets", "value": len(by_bucket)},
            ],
            "rule": (
                "wealth.client_stock_exposure joined to atlas_foundation.instrument_master on "
                "instrument_id for sector; only the atlas_scored_stock bucket resolves to a "
                "sector (other buckets — etf_units, cash_other, debt_instrument, "
                "identified_stock_unscored, indian_stock_unidentified, foreign_stock, other — "
                "have no scored sector). Identified pct = atlas_scored_stock exposure / total "
                "exposure for THIS client, computed fresh, not the book-wide ~67% figure."
            ),
            "assumptions": [],
            "steps": [{"label": "Rows for this client", "value": len(rows)}],
            "sample_rows": [
                {"bucket": b, "sector": s, "exposure_rs": _f(e)} for b, s, e in rows[:20]
            ],
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }


def client_funds_table(conn, client_id: int) -> dict:
    """This client's own funds table (Q1 slice): every held fund's value,
    category (asset_class — same field Q1 calls 'category'), and per-fund
    verdict from wealth.fund_performance where scored (build_fund_performance.py
    only scores held EQUITY funds — other asset classes have no verdict,
    rendered as a gap, never a fabricated one)."""
    cur = conn.cursor()
    cur.execute(
        """select h.scheme_id, s.display_name, s.asset_class, h.market_value::float,
                  fp.verdict
           from wealth.holdings h
           join wealth.schemes s using (scheme_id)
           left join wealth.fund_performance fp using (scheme_id)
           where h.client_id = %s and h.market_value > 0
           order by h.market_value desc""",
        (client_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "no held funds for this client",
            "working": {
                "inputs": [],
                "rule": "wealth.holdings has no market_value > 0 rows for this client_id",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    total = sum(v for *_rest, v, _vd in rows)
    funds = [
        {"scheme_id": sid, "fund": name, "category": cat, "value_rs": _f(v), "verdict": vd}
        for sid, name, cat, v, vd in rows
    ]
    n_scored = sum(1 for f in funds if f["verdict"])
    verdict = (
        f"{len(funds)} funds held, {lcr_py(total)} total; {n_scored} scored for fund "
        "performance."
    )

    return {
        "client_id": client_id,
        "total_value_rs": _f(total),
        "n_funds": len(funds),
        "n_scored": n_scored,
        "funds": funds,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Held funds", "value": len(funds)},
                {"label": "Total value", "value": _f(total)},
                {"label": "Funds scored (fund_performance)", "value": n_scored},
            ],
            "rule": (
                "wealth.holdings joined to wealth.schemes for held value/category (same "
                "convention as book-level Q1's client_id, scheme_id, display_name, "
                "asset_class, market_value select) and left-joined to wealth.fund_performance "
                "for this client's own held-fund verdict — that table only scores held "
                "EQUITY funds (build_fund_performance.py), so non-equity holdings show no "
                "verdict."
            ),
            "assumptions": [],
            "steps": [{"label": "Rows for this client", "value": len(rows)}],
            "sample_rows": [
                {
                    "fund": f["fund"],
                    "category": f["category"],
                    "value_rs": f["value_rs"],
                    "verdict": f["verdict"],
                }
                for f in funds[:20]
            ],
            "sample_of": len(funds),
            "honesty": "exact",
        },
    }


def client_label_check(conn, client_id: int) -> dict:
    """This client's own label-check hits (Q2 slice): held funds joined to
    wealth.fund_label_check, same verdict vocabulary as book-level Q2
    (mismatch/match/no_data), scoped to just this client's holdings."""
    cur = conn.cursor()
    cur.execute(
        """select h.scheme_id, s.display_name, flc.category, flc.verdict, flc.detail,
                  h.market_value::float
           from wealth.holdings h
           join wealth.schemes s using (scheme_id)
           join wealth.fund_label_check flc using (scheme_id)
           where h.client_id = %s and h.market_value > 0
           order by h.market_value desc""",
        (client_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {
            "client_id": client_id,
            "insufficient": True,
            "message": "no label-checked funds held by this client",
            "working": {
                "inputs": [],
                "rule": "wealth.fund_label_check has no row for any fund this client holds",
                "assumptions": [],
                "steps": [],
                "sample_rows": [],
                "sample_of": 0,
                "honesty": None,
            },
        }

    funds = [
        {
            "scheme_id": sid,
            "fund": name,
            "category": cat,
            "verdict": vd,
            "detail": detail,
            "value_rs": _f(v),
        }
        for sid, name, cat, vd, detail, v in rows
    ]
    mismatches = [f for f in funds if f["verdict"] == "mismatch"]
    mismatch_value = sum(f["value_rs"] or 0.0 for f in mismatches)
    verdict = (
        f"{len(mismatches)} of {len(funds)} held funds carry a label mismatch; "
        f"{lcr_py(mismatch_value)}."
    )

    return {
        "client_id": client_id,
        "n_funds": len(funds),
        "n_mismatch": len(mismatches),
        "mismatch_value_rs": _f(mismatch_value),
        "funds": funds,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Held label-checked funds", "value": len(funds)},
                {"label": "Mismatch funds", "value": len(mismatches)},
                {"label": "Value in mismatch funds", "value": _f(mismatch_value)},
            ],
            "rule": (
                "wealth.fund_label_check joined to wealth.holdings for this client's held "
                "value, same verdict vocabulary as book-level Q2 (SEBI large/mid/small "
                "cap-mandate vs the fund's actual disclosed composition, per "
                "build_label_check.py's CATEGORY_RULES)."
            ),
            "assumptions": [],
            "steps": [{"label": "Rows for this client", "value": len(rows)}],
            "sample_rows": [
                {
                    "fund": f["fund"],
                    "category": f["category"],
                    "verdict": f["verdict"],
                    "value_rs": f["value_rs"],
                }
                for f in funds[:20]
            ],
            "sample_of": len(funds),
            "honesty": "exact",
        },
    }
