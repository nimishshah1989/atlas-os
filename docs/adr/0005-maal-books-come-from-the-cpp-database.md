# 0005 — The MaaL books are synced from the client portal, not folded from recommendations

- **Status:** Accepted (2026-07-31)
- **Context chunk:** MaaL Process (formerly Monday confirmations)
- **Supersedes in part:** [ADR 0003](0003-monday-confirmations-book-state.md), Decision 2

## Context

[ADR 0003](0003-monday-confirmations-book-state.md) built the weekly document as a
self-contained artifact: publishing folded the FM's calls onto last week's book and
stored the result, and the next week read that back.

That is wrong, and the reason is a fact about the desk rather than about the code.
**The FM's buy/sell calls are a superset of what actually executes.** A week's
recommendations are a comprehensive set; what fills through the week is a subset.
So the folded book diverged from the real portfolio every week it compounded, and
the circulated PDF published that divergence as the Model Portfolio.

The real portfolios live in the `clients.jslwealth.in` (CPP) database as three UCCs:
`BJ53` (Leaders), `BJ53IND` (IND11), `JR100PASS` (Passive).

## Decision 1 — the opening book is the latest synced snapshot of the real portfolio

A twice-daily job reads CPP and writes `maal_holding_snapshot`. The Monday book opens
from the most recent snapshot, not from `resulting_book`.

*Rejected:* continuing to fold. It is self-referential — it can only ever tell you what
the FM said, never what the desk did, and the gap widens monotonically.

`resulting_book` is still written at publish and still freezes a published report so it
renders identically forever (ADR 0003's Decision 2 stands for that purpose). It simply no
longer feeds the following week.

## Decision 2 — CPP owns what is held and at what cost; Atlas owns what it is worth

The sync reads `isin`, `quantity` and `avg_cost`. It ignores CPP's `current_price` and
`weight_pct` entirely and marks every position with Atlas's own NSE close.

*Rejected:* importing CPP's valuation. Its `weight_pct` divides by invested value alone,
so its weights always sum to 100 and **cash reads 0%** — for a document whose whole
purpose is showing the FM what is deployed and what is not, that is the one number you
cannot get wrong.

Cash is `cash_value + bank_balance + etf_value`, where `etf_value` is CPP's liquid-ETF
sleeve (LIQUIDBEES / LIQUIDCASE / LIQUIDETF). The FM's rule is that liquid ETFs *are*
cash. GOLDBEES and SILVERBEES are not: they are asset-class exposure, and CPP classifies
them EQUITY. This reproduces CPP's own `cash_pct` exactly on all three books.

## Decision 3 — a dated snapshot, not a delta table

One row per position per day, never overwritten. Yesterday versus today is a query.

*Rejected:* storing computed changes. Two representations of the same fact drift, and the
diff is derivable from data we already keep.

`cpp_holdings` is current-state only, so this is also the only reason a historical book
exists at all: if Atlas does not record it daily, "what did BJ53 hold last Friday" is
unanswerable.

## Decision 4 — two dates on every snapshot row

`as_of` is when Atlas looked; `source_as_of` is the day CPP's data is from
(`cpp_nav_series.nav_date`). The board and the PDF render `source_as_of`.

*Rejected:* one date. CPP positions only move when a backoffice file is uploaded, so the
two diverge routinely — on the first real sync all three books were a day behind. A book
stamped Monday that actually holds Thursday's positions is how the desk sells a name that
was already sold. Keeping both also distinguishes a **dead sync** ("we never looked") from
a quiet one ("we looked, nothing changed"), which the freshness guard treats as different
severities: dead is blocking, lagging is a warning.

## Consequences

- **Atlas reads a second database.** This is an ingestion boundary like bhavcopy or AMFI,
  not a runtime dependency — the board never queries CPP during a page load. Access is a
  dedicated `atlas_reader` role with SELECT on four tables and no reach into `cpp_clients`,
  which holds client PII.
- **`portfolio_master` registration is what makes the portfolio pages work.** Nothing was
  written in the frontend; `/portfolios` and the detail pages populate because the rows
  exist in tables they already read.
- **One writer per NAV row.** `portfolio_run`'s mark and backtest loops now exclude
  `params.source = 'cpp'`. They previously selected every active portfolio, so the engine's
  nightly mark would have overwritten synced NAV with computed values.
- **Realized P&L is measured, not inferred.** `cpp_transactions` carries the real traded
  price, so FIFO produces figures reconcilable against the client statement. Inferring P&L
  from snapshot diffs would have been wrong by the intraday spread on every sell.

## Smaller choices worth recording

- **`CORPUS_IN` opens a lot.** It is a securities transfer-in with a real quantity and
  price, not cash. Modelling it as cash left 42 of 991 real sells with no cost basis and
  silently suppressed ₹8.11 lakh of realized P&L. Found by running FIFO over the real
  history, not by review.
- **`BONUS` is excluded from the trade log by a CHECK, not by choice.** Bonus shares arrive
  at price 0 and `portfolio_trades` has `CHECK (price > 0)`. FIFO still opens a zero-cost
  lot for them, so realized P&L is unaffected; only the log omits them.
- **`portfolio_trades.instrument_key` is the instrument UUID**, matching the engine. The
  readable `stock:SYMBOL` form lives only in `maal_holding_snapshot`. Writing the readable
  form into `portfolio_trades` made `getPortfolioDetail`'s `::uuid[]` cast throw, and every
  detail page 404'd while the list page looked fine.
- **Idempotency lives in `maal_trade_link`**, not a column on `portfolio_trades`. A link
  table touches nothing the engine owns, and the insert and link share one transaction — a
  crash between them would double the book's history on the next run.
- **Money never passes through pandas.** `read_sql` coerces postgres `numeric` to float64.
  Rows come back through SQLAlchemy so Decimals stay Decimals.
