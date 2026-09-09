#!/usr/bin/env python3
"""Form N-PORT-P → ``atlas_global.etf_holdings`` and ``atlas_global.etf_meta``.

    python scripts/global_market/ingest_nport.py                          # weekly increment
    python scripts/global_market/ingest_nport.py --symbols IVV,TQQQ --dry-run
    python scripts/global_market/ingest_nport.py --in-universe --limit 200 --report /tmp/n.csv

WHAT THIS IS FOR. Before it, ``etf_meta``, ``etf_holdings``, ``etf_shares_daily`` and
``etf_exposure_daily`` had ZERO producers: the board could say a fund's price had gone up and
that a regular expression thought it was a semiconductor fund, and nothing else. The cost lens
scored one of its four sub-scores and the quality lens none of its own. This is the feed that
says what a fund HOLDS and what it is WORTH, and it is free, official and machine-readable.

WHAT IT IS NOT. N-PORT carries no expense ratio, no shares outstanding and no inception date,
so the cost lens's expense sub-score still waits on an issuer feed and ``etf_shares_daily``
stays empty on purpose: its documented job is the flow lens's Δ-shares-21d proxy, and four
points a year in a table named "daily" would look like a series without being one.

THE CADENCE IS THE FILER'S, NOT THE CALENDAR'S. Funds file monthly and only the third month of
each of their FISCAL quarters becomes public, about sixty days later. iShares reports 30 June,
ProShares 31 May. So ``as_of_date`` is whatever the document says (``repPdDate``) and a
snapshot is two months old the day it appears — shown on the card as ``holdings_as_of``, never
implied to be today.

INCREMENTAL, IDEMPOTENT, AND IT COMMITS AS IT GOES. One small index request per fund tells us
the newest accession; the document is fetched only when that accession is not the one already
loaded (``ingest_state``, source ``nport``, keyed by instrument), so between quarters a run is
one cheap request per fund and no download at all (``--full`` re-fetches regardless).
``etf_holdings`` is append-only by snapshot: a re-run writes the same rows over themselves and
an amendment (NPORT-P/A) restates its own period. And AGG's filing alone is 13,269 holdings in
15.9 MB against IVV's 508 in 512 KB, so a first pass is millions of records — staging them all
for one transaction is how a two-vCPU box runs out of memory and how an interruption at hour
three loses hour one. Every :data:`FLUSH_ROWS` the batch is written with the watermarks of the
funds in it, and the next run resumes from there.

AUM IS THE SERIES', AND SOMETIMES THAT IS NOT THE ETF'S. See the ``series_net_assets_usd``
comment in ``ddl/02_etf.sql``: ``aum_usd`` is filled only for a single-class series. A
multi-class one (every Vanguard ETF) keeps the series figure under its own name and no AUM at
all, because the number that would go there is not the fund's (rule #0).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
import psycopg2
from _report import Report
from psycopg2.extras import execute_values

from atlas.global_market.providers.nport import FilingRef, FundFacts, NportProvider, parse_nport

M = _gdb.M
SOURCE = "edgar"  # provider_calls key — the same provider as company facts and identity
SOURCE_LABEL = "nport"  # etf_holdings.source / etf_meta.aum_source, both CHECK-constrained
STATE_SOURCE = "nport"  # ingest_state.source
HOLDINGS_TABLE = f"{M}.etf_holdings"
META_TABLE = f"{M}.etf_meta"

# CUSIP and ISIN reach instrument_master through symbol_alias, which is exactly what that
# table is for ("that source's own spelling"). ingest_index_membership.py writes them from the
# SSGA SPY workbook, whose Identifier column IS the CUSIP — so the bridge covers the S&P 500,
# which is precisely the population lookthrough_scored_w is defined over.
ALIAS_SOURCES = ("cusip", "isin")

HOLDING_DB_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "as_of_date",
    "holding_key",
    "holding_instrument_id",
    "holding_name",
    "holding_ticker",
    "cusip",
    "isin",
    "weight_frac",
    "market_value_usd",
    "balance",
    "units",
    "country_iso2",
    "asset_category",
    "payoff_profile",
    "derivative_category",
)
META_DB_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "aum_usd",
    "aum_as_of",
    "aum_source",
    "series_net_assets_usd",
    "series_class_count",
    "derivative_notional_share",
    "derivatives_share",
    "source",
)

# The columns the parser already produces under the table's own names — carried across by
# name so the two lists cannot drift apart in a rename.
_KEYED = ("instrument_id", "as_of_date", "holding_instrument_id")
CARRIED_COLUMNS: tuple[str, ...] = tuple(c for c in HOLDING_DB_COLUMNS if c not in _KEYED)

# Rows are written in batches, not in one transaction at the end. AGG's own filing carries
# 13,269 holdings in a 15.9 MB document (measured 2026-09-09) against IVV's 508, so a full
# first pass over several thousand funds is millions of records — holding them all in memory
# before the first INSERT is how a 2-vCPU box runs out of it. A batch also makes a long first
# run RESUMABLE: what committed is watermarked, and the re-run skips it.
FLUSH_ROWS = 50_000

STATUS_WRITTEN = "written"
STATUS_UNCHANGED = "unchanged"
STATUS_NO_FILING = "no_filing"
STATUS_NO_HOLDINGS = "no_holdings"
STATUS_SERIES_MISMATCH = "series_mismatch"
STATUS_WEIGHT_OUT_OF_RANGE = "weight_out_of_range"
STATUS_FETCH_FAILED = "fetch_failed"
STATUS_PARSE_FAILED = "parse_failed"
FAILURE_STATUSES = (STATUS_NO_FILING, STATUS_NO_HOLDINGS, STATUS_SERIES_MISMATCH,
                    STATUS_WEIGHT_OUT_OF_RANGE, STATUS_FETCH_FAILED,
                    STATUS_PARSE_FAILED)  # fmt: skip
# etf_holdings.chk_etf_holdings_weight_frac — the TABLE's bound, not a methodology number. One
# filer's impossible pctVal would abort a whole 50,000-row batch over hundreds of innocent
# funds, so the fund is refused and reported instead.
WEIGHT_LIMIT = Decimal(10)
# The per-fund outcome CSV. ``outcome()`` names its cells after these, so a column added here
# without a value is empty rather than shifted into its neighbour's place.
REPORT_COLUMNS = ("symbol", "series_id", "instrument_id", "status", "accession", "filed",
                  "period", "holdings", "resolved", "sum_abs_weight", "net_assets_usd",
                  "classes", "detail")  # fmt: skip


# ── database ──────────────────────────────────────────────────────────────────────────────

ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.universe_snapshot WHERE date <= :cutoff"

# Every active ETF the SEC gave a series id, most heavily traded first, so a --limit run
# covers the funds the board actually shows. The universe join is LEFT: a fund below the
# liquidity floor is still classified (plan: "every US-listed ETF is classified; scoring and
# basket eligibility above a liquidity floor"), so its holdings are still worth having.
TARGETS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.series_id,
       us.adv_usd_median_60d, coalesce(us.in_universe, false) AS in_universe
FROM {M}.instrument_master im
LEFT JOIN {M}.universe_snapshot us
       ON us.instrument_id = im.instrument_id AND us.date = :anchor
WHERE im.asset_class = 'etf' AND im.is_active AND im.series_id IS NOT NULL
ORDER BY us.adv_usd_median_60d DESC NULLS LAST, im.symbol
"""

WATERMARK_SQL = f"SELECT key, value FROM {M}.ingest_state WHERE source = :source"
ALIAS_SQL = (
    f"SELECT source_symbol, instrument_id::text AS instrument_id FROM {M}.symbol_alias "
    f"WHERE source IN ({', '.join(repr(s) for s in ALIAS_SOURCES)}) AND valid_to IS NULL"
)

HOLDINGS_UPSERT_SQL = f"""
insert into {HOLDINGS_TABLE} ({", ".join(HOLDING_DB_COLUMNS)}, source, ingested_at)
values %s
on conflict (instrument_id, as_of_date, holding_key) do update set
    {
    ", ".join(
        f"{c} = excluded.{c}"
        for c in HOLDING_DB_COLUMNS
        if c not in ("instrument_id", "as_of_date", "holding_key")
    )
},
    source = excluded.source, ingested_at = now()
"""

META_UPSERT_SQL = f"""
insert into {META_TABLE} ({", ".join(META_DB_COLUMNS)}, updated_at)
values %s
on conflict (instrument_id) do update set
    {", ".join(f"{c} = excluded.{c}" for c in META_DB_COLUMNS if c != "instrument_id")},
    updated_at = now()
"""


def anchor_date(cutoff: dt.date) -> dt.date | None:
    """The latest universe snapshot at or before the EOD, or ``None``.

    Unlike the stock ingests this is not fatal: the snapshot only ORDERS the work here, and a
    database that has not run ``build_universe_snapshot.py`` yet still has ETFs whose holdings
    are worth fetching. ``--in-universe`` is the one flag that needs it, and says so.

    ``max()`` over no rows is ONE row holding NULL, not an empty frame — and ``NaT is None`` is
    False, so that refusal would never fire on an emptiness test alone.
    """
    frame = _gdb.read_df(ANCHOR_SQL, {"cutoff": cutoff})
    if frame.empty or pd.isna(frame["d"].iloc[0]):
        return None
    return frame["d"].iloc[0]


def targets(
    anchor: dt.date | None, symbols: str | None, limit: int | None, in_universe: bool
) -> pd.DataFrame:
    frame = _gdb.read_df(TARGETS_SQL, {"anchor": anchor})
    if in_universe:
        if anchor is None:
            raise SystemExit(
                "REFUSED: --in-universe needs a universe_snapshot — run "
                "build_universe_snapshot.py, or drop the flag to take every ETF with a series"
            )
        frame = pd.DataFrame(frame[frame["in_universe"]])
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        frame = pd.DataFrame(frame[frame["symbol"].isin(sorted(wanted))])
        missing = wanted - set(frame["symbol"])
        if missing:
            raise SystemExit(
                "REFUSED: not active ETFs with an SEC series id: " + ", ".join(sorted(missing))
            )
    return pd.DataFrame(frame.head(limit)) if limit else frame


def watermarks() -> dict[str, dict[str, Any]]:
    """``instrument_id → {accession, filed, period, …}`` of the filing already loaded."""
    frame = _gdb.read_df(WATERMARK_SQL, {"source": STATE_SOURCE})
    return {k: v for k, v in zip(frame["key"], frame["value"], strict=True) if isinstance(v, dict)}


def alias_map() -> dict[str, str]:
    """``CUSIP | ISIN → instrument_id``, upper-cased, for the look-through resolution."""
    frame = _gdb.read_df(ALIAS_SQL)
    pairs = zip(frame["source_symbol"], frame["instrument_id"], strict=True)
    return {str(key).strip().upper(): iid for key, iid in pairs}


# ── the tables' records ───────────────────────────────────────────────────────────────────


def holding_rows(
    holdings: pd.DataFrame, instrument_id: str, as_of: dt.date, aliases: Mapping[str, str]
) -> tuple[list[dict[str, Any]], int]:
    """``(etf_holdings records, how many resolved to a scored instrument)``.

    Resolution is by CUSIP then ISIN, never by ticker: the only ``ticker`` elements in the
    fixtures are on futures lines (``ESU6``), and a futures code that happened to collide with
    a listed symbol would put a fund's index hedge into the look-through as an equity.
    """
    records: list[dict[str, Any]] = []
    resolved = 0
    for row in holdings.to_dict("records"):
        held = next(
            (
                aliases[key]
                for raw in (row["cusip"], row["isin"])
                if raw and (key := str(raw).strip().upper()) in aliases
            ),
            None,
        )
        resolved += held is not None
        records.append(
            {"instrument_id": instrument_id, "as_of_date": as_of, "holding_instrument_id": held}
            | {c: row[c] for c in CARRIED_COLUMNS}
        )
    return records, resolved


def abs_weight(holdings: pd.DataFrame, only: str | None = None) -> Decimal | None:
    """Σ|weight_frac| over the snapshot, or over the lines carrying ``only``.

    ``only="derivative_category"`` is the DDL's "fraction of NAV in derivatives": a line is a
    derivative because it filed a ``derivativeInfo`` block, not because its ``assetCat`` is one
    of a dozen codes this file would have to remember correctly to avoid under-counting.
    """
    if holdings.empty:
        return None
    rows = holdings if only is None else holdings.loc[holdings[only].notna()]
    return sum((abs(w) for w in rows["weight_frac"] if w is not None), Decimal(0))


def meta_row(facts: FundFacts, instrument_id: str, holdings: pd.DataFrame) -> dict[str, Any]:
    """One ``etf_meta`` record. ``aum_usd`` is the series' net assets ONLY where the series has
    one share class; see the module docstring."""
    single = facts.class_count == 1
    return {
        "instrument_id": instrument_id,
        "aum_usd": facts.net_assets if single else None,
        "aum_as_of": facts.period_date if single and facts.net_assets is not None else None,
        "aum_source": SOURCE_LABEL if single and facts.net_assets is not None else None,
        "series_net_assets_usd": facts.net_assets,
        "series_class_count": facts.class_count or None,
        "derivative_notional_share": facts.derivative_notional_share,
        "derivatives_share": abs_weight(holdings, only="derivative_category"),
        "source": SOURCE_LABEL,
    }


# ── run ───────────────────────────────────────────────────────────────────────────────────


def run(
    *,
    eod: dt.date,
    symbols: str | None,
    limit: int | None,
    in_universe: bool,
    full: bool,
    dry_run: bool,
    report: Report | None,
) -> dict[str, int]:
    anchor = anchor_date(eod)
    picked = targets(anchor, symbols, limit, in_universe)
    if picked.empty:
        raise SystemExit(
            f"REFUSED: no active ETF in {M}.instrument_master carries an SEC series id — "
            "run build_identity.py first; the series id is how a fund reaches its filings"
        )
    marks = {} if full else watermarks()
    aliases = alias_map()
    provider = NportProvider()
    print(
        f"[nport] anchor={anchor} funds={len(picked):,d} loaded={len(marks):,d} "
        f"cusip/isin aliases={len(aliases):,d}"
    )
    if not aliases:  # ingest_index_membership.py writes them from the SSGA workbook
        print("  NOTE: no cusip/isin aliases — every holding_instrument_id will be NULL")

    holdings_out: list[dict[str, Any]] = []
    meta_out: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter({"attempted": len(picked)})

    def flush() -> None:
        """Commit what is staged and let go of it — under ``--dry-run`` only let go of it, so a
        rehearsal over the whole universe costs no more memory than a real run."""
        if not holdings_out:
            return
        if not dry_run:
            write(holdings_out, meta_out, states, eod, counts)
            print(
                f"  … committed {len(holdings_out):,d} row(s) over {len(meta_out):,d} fund(s) "
                f"({counts[STATUS_WRITTEN]:,d} of {len(picked):,d} done)"
            )
        counts["rows_written"] += len(holdings_out)
        holdings_out.clear()
        meta_out.clear()
        states.clear()

    try:
        for row in picked.to_dict("records"):
            counts.update(
                _one_fund(row, provider, marks, aliases, holdings_out, meta_out, states, report)
            )
            if len(holdings_out) >= FLUSH_ROWS:
                flush()
        flush()
    finally:  # the budget was spent whatever the run decides next
        _gdb.commit_provider_calls(eod, {SOURCE: provider.calls})

    if dry_run:
        print(
            f"  --dry-run: nothing written ({counts['rows_written']:,d} row(s) over "
            f"{counts[STATUS_WRITTEN]:,d} fund(s) would have been)"
        )
    else:
        print(
            f"  upserted {counts['rows_written']:,d} row(s) into {HOLDINGS_TABLE} and "
            f"{META_TABLE}; {counts['resolved']:,d} resolved to a scored instrument"
        )
    _summarise(counts, report, provider.calls)
    return dict(counts)


def _one_fund(
    row: Mapping[str, Any],
    provider: NportProvider,
    marks: Mapping[str, Mapping[str, Any]],
    aliases: Mapping[str, str],
    holdings_out: list[dict[str, Any]],
    meta_out: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    report: Report | None,
) -> Counter[str]:
    """Fetch, parse and stage one fund. One fund's failure is a reported outcome, never the end
    of the run — the other five thousand are still worth writing."""
    symbol, series, iid = row["symbol"], row["series_id"], row["instrument_id"]

    def outcome(status: str, detail: str, **cells: Any) -> Counter[str]:
        """One report line and the counters its outcome moves. ``cells`` are named for the
        report's own columns, so a column added there cannot silently take another's value."""
        if report is not None:
            named = cells | {"symbol": symbol, "series_id": series, "instrument_id": iid}
            named |= {"status": status, "detail": detail}
            unknown = set(named) - set(REPORT_COLUMNS)
            assert not unknown, f"outcome() named non-columns {sorted(unknown)}"
            report.add(*(named.get(c) for c in REPORT_COLUMNS))
        found = cells.get("resolved")
        return Counter({status: 1, "resolved": int(found) if isinstance(found, int) else 0})

    try:
        refs = provider.fetch_filings(series)
    except Exception as e:  # any transport failure is this fund's outcome, not the run's
        return outcome(STATUS_FETCH_FAILED, f"index: {type(e).__name__}: {e}")
    if not refs:
        return outcome(STATUS_NO_FILING, "no N-PORT-P on file for this series")

    ref: FilingRef = refs[0]  # newest filed; an amendment restates its own period
    known = marks.get(iid) or {}
    if known.get("accession") == ref.accession:
        return outcome(
            STATUS_UNCHANGED,
            "already loaded",
            accession=ref.accession,
            filed=ref.filed,
            period=known.get("period"),
        )

    try:
        document = provider.fetch_primary_doc(ref)
    except Exception as e:
        return outcome(
            STATUS_FETCH_FAILED, f"document: {type(e).__name__}: {e}", accession=ref.accession
        )
    try:
        facts, holdings = parse_nport(document)
    except Exception as e:  # a filer's own malformed XML is a reported outcome, not a crash
        return outcome(
            STATUS_PARSE_FAILED,
            f"{type(e).__name__}: {e}",
            accession=ref.accession,
            filed=ref.filed,
        )

    if facts.series_id and facts.series_id != series:
        # EDGAR handed back a document for a different series: write nothing rather than file
        # one fund's holdings under another's name.
        return outcome(
            STATUS_SERIES_MISMATCH,
            f"document is series {facts.series_id}",
            accession=ref.accession,
            filed=ref.filed,
            period=facts.period_date,
        )

    heavy = [
        key
        for key, w in zip(holdings["holding_key"], holdings["weight_frac"], strict=True)
        if w is not None and abs(w) > WEIGHT_LIMIT
    ]
    if heavy:
        # The table's CHECK would abort the whole batch — hundreds of innocent funds with it.
        return outcome(
            STATUS_WEIGHT_OUT_OF_RANGE,
            f"{len(heavy)} line(s) over |{WEIGHT_LIMIT}| of NAV, first {heavy[0]!r}",
            accession=ref.accession,
            filed=ref.filed,
            period=facts.period_date,
            holdings=len(holdings),  # no sum_abs_weight: a Σ over an impossible weight is noise
        )

    records, resolved = holding_rows(holdings, iid, facts.period_date, aliases)
    if not records:
        return outcome(
            STATUS_NO_HOLDINGS,
            "the filing reports no positions",
            accession=ref.accession,
            filed=ref.filed,
            period=facts.period_date,
            net_assets_usd=facts.net_assets,
            classes=facts.class_count,
        )

    holdings_out.extend(records)
    meta_out.append(meta_row(facts, iid, holdings))
    states[iid] = {
        "symbol": symbol,
        "series_id": series,
        "accession": ref.accession,
        "form": ref.form,
        "filed": ref.filed.isoformat(),
        "period": facts.period_date.isoformat(),
        "holdings": len(records),
        "resolved": resolved,
        "classes": facts.class_count,
    }
    return outcome(
        STATUS_WRITTEN,
        ref.form,
        accession=ref.accession,
        filed=ref.filed,
        period=facts.period_date,
        holdings=len(records),
        resolved=resolved,
        sum_abs_weight=abs_weight(holdings),
        net_assets_usd=facts.net_assets,
        classes=facts.class_count,
    )


def write(
    holdings: Sequence[Mapping[str, Any]],
    meta: Sequence[Mapping[str, Any]],
    states: Mapping[str, Mapping[str, Any]],
    eod: dt.date,
    counts: Counter[str],
) -> None:
    """The rows and every per-fund watermark, in ONE transaction — both or neither. A watermark
    that survived a rolled-back write would claim a snapshot that is not there."""
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            if holdings:
                execute_values(
                    cur,
                    HOLDINGS_UPSERT_SQL,
                    [tuple(r[c] for c in HOLDING_DB_COLUMNS) for r in holdings],
                    template="("
                    + ", ".join(["%s"] * len(HOLDING_DB_COLUMNS))
                    + f", '{SOURCE_LABEL}', now())",
                    page_size=1000,
                )
            if meta:
                execute_values(
                    cur,
                    META_UPSERT_SQL,
                    [tuple(r[c] for c in META_DB_COLUMNS) for r in meta],
                    template="(" + ", ".join(["%s"] * len(META_DB_COLUMNS)) + ", now())",
                    page_size=500,
                )
            for instrument_id, state in states.items():
                _gdb.record_state(cur, STATE_SOURCE, instrument_id, state)
            _gdb.record_state(
                cur,
                STATE_SOURCE,
                "etf_holdings",
                {
                    "eod": eod.isoformat(),
                    "funds_attempted": counts["attempted"],
                    "funds_written": counts[STATUS_WRITTEN],
                    "funds_unchanged": counts[STATUS_UNCHANGED],
                    "holding_rows": counts["rows_written"] + len(holdings),
                    "resolved_rows": counts["resolved"],
                    "failures": {s: counts[s] for s in FAILURE_STATUSES if counts[s]},
                    "run_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )
    finally:
        conn.close()


def _summarise(counts: Counter[str], report: Report | None, calls: Mapping[str, int]) -> None:
    print(
        f"  {counts[STATUS_WRITTEN]:,d} written · {counts[STATUS_UNCHANGED]:,d} unchanged · "
        + " · ".join(f"{counts[s]:,d} {s}" for s in FAILURE_STATUSES)
    )
    print("  requests: " + ", ".join(f"{k}={v:,d}" for k, v in sorted(calls.items())))
    if report is not None:
        print(f"  per-fund outcomes {report.where()}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbols", help="comma-separated ETF symbols instead of the whole universe")
    p.add_argument("--limit", type=int, help="stop after N funds (heaviest ADV$ first)")
    p.add_argument(
        "--in-universe", action="store_true", help="only funds above the liquidity floor"
    )
    p.add_argument(
        "--full", action="store_true", help="ignore the watermarks and re-fetch every document"
    )
    p.add_argument("--dry-run", action="store_true", help="fetch and parse, write nothing")
    p.add_argument("--report", type=Path, help="CSV of the per-fund outcome")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    report = Report(args.report, REPORT_COLUMNS) if args.report else Report(None, REPORT_COLUMNS)
    try:
        counts = run(
            eod=_gdb.eod_cutoff(),
            symbols=args.symbols,
            limit=args.limit,
            in_universe=args.in_universe,
            full=args.full,
            dry_run=args.dry_run,
            report=report,
        )
    finally:
        report.close()
    return 0 if counts.get(STATUS_WRITTEN) or counts.get(STATUS_UNCHANGED) else 1


if __name__ == "__main__":
    raise SystemExit(main())
