-- MaaL: mirror CPP's own numbers into Atlas. Atlas computes NONE of them.
--
-- Applied via: python3 -c "import _db; _db.exec_script(open('maal_cpp_ddl.sql').read())"
--
-- Why a mirror at all, rather than the frontend reading CPP live: the board is
-- self-contained (CLAUDE.md rule 2) and reads atlas_foundation only. So the numbers
-- must land here — but they land as a COPY. The moment Atlas derives one of these
-- figures instead of copying it, the two systems drift, and the drift shows up on a
-- client page as a 4,975.1% return with nothing objecting.

-- ── CPP's risk metrics, verbatim ─────────────────────────────────────────────
-- One row per book per computed_date. Column names are cpp_risk_metrics' own names,
-- unchanged, so a reconciliation is a field-for-field comparison and not a mapping
-- exercise — see atlas/maal/cpp_metrics.COPIED_FIELDS, which is the same list.
--
-- Only 18 of CPP's 146 columns are here. The list is "what the board displays": a
-- figure that is displayed but not copied cannot be reconciled, and a figure that is
-- copied but not displayed is dead weight. Adding a figure to a page means adding it
-- to COPIED_FIELDS, to this table, and to the view below — the gate fails until it is.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_cpp_metrics (
    maal_code      text NOT NULL CHECK (maal_code IN ('leaders', 'passive', 'ind11')),
    -- CPP's own stamp for when it computed these, NOT when we looked. CPP does not
    -- compute every day (15 rows over the 32 days to 2026-08-07), so a run date here
    -- would claim a freshness the data does not have.
    computed_date  date NOT NULL,
    -- The book's first nav_date in CPP. Stored rather than read from
    -- portfolio_master.inception_date so the age rule below is driven by the same
    -- source as the figures it withholds.
    inception_date date NOT NULL,
    -- Generated, so no caller can compute a book's age slightly differently from the
    -- view that gates on it.
    age_days       integer GENERATED ALWAYS AS (computed_date - inception_date) STORED,

    absolute_return        numeric,   -- the headline: CPP's Modified-Dietz adjusted return
    cagr                   numeric,
    xirr                   numeric,
    return_1m              numeric,
    return_3m              numeric,
    return_6m              numeric,
    return_1y              numeric,
    bench_return_inception numeric,
    bench_return_1m        numeric,
    bench_return_3m        numeric,
    bench_return_6m        numeric,
    bench_return_1y        numeric,
    max_drawdown           numeric,
    volatility             numeric,
    sharpe_ratio           numeric,
    sortino_ratio          numeric,
    alpha                  numeric,
    beta                   numeric,

    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (maal_code, computed_date)
);

-- ── CPP's NAV series, verbatim and WHOLE ─────────────────────────────────────
-- 4,045 rows across the three books as of 2026-08-07, back to 2020-09-28. The sync
-- used to keep only the newest row (DISTINCT ON ... LIMIT 1), which is why a six-year
-- book charted as four points.
--
-- Its own table rather than portfolio_nav_daily: that table is the ENGINE's shape and
-- requires n_positions NOT NULL, which no historical CPP row can honour — cpp_holdings
-- is current-state only, so the position count on 2021-03-04 does not exist anywhere.
-- Writing a 0 there would be inventing a number (rule #0). portfolio_nav_daily keeps
-- receiving today's row, unchanged; the gate reconciles both against CPP.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_cpp_nav (
    maal_code       text NOT NULL CHECK (maal_code IN ('leaders', 'passive', 'ind11')),
    nav_date        date NOT NULL,
    nav_value       numeric,
    current_value   numeric,
    invested_amount numeric,
    benchmark_value numeric,
    cash_pct        numeric,
    cash_value      numeric,
    bank_balance    numeric,
    etf_value       numeric,
    synced_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (maal_code, nav_date)
);

-- ── The read surface ─────────────────────────────────────────────────────────
-- Everything that renders a MaaL figure reads THIS, not the table. The FM's rule —
-- XIRR and CAGR only past one year — lives here, in the one place every reader must
-- pass through, rather than in each page that happens to remember it. A display
-- convention is something someone forgets; a view is not.
--
-- Withheld figures come back NULL, never 0 and never a substituted absolute return:
-- the caller renders an em-dash and the period returns beside it stay real.
CREATE OR REPLACE VIEW atlas_foundation.maal_book_metrics AS
SELECT DISTINCT ON (maal_code)
    maal_code,
    computed_date,
    inception_date,
    age_days,
    age_days >= 365 AS annualised_ok,

    absolute_return,
    -- The two annualisation artefacts, and the only two fields this view alters.
    CASE WHEN age_days >= 365 THEN cagr END AS cagr,
    CASE WHEN age_days >= 365 THEN xirr END AS xirr,
    -- Absolute period returns, never annualised, so they stand for a young book.
    -- CPP already NULLs the windows a young book has not lived through.
    return_1m,
    return_3m,
    return_6m,
    return_1y,
    bench_return_inception,
    bench_return_1m,
    bench_return_3m,
    bench_return_6m,
    bench_return_1y,
    max_drawdown,
    volatility,
    sharpe_ratio,
    sortino_ratio,
    alpha,
    beta
FROM atlas_foundation.maal_cpp_metrics
ORDER BY maal_code, computed_date DESC;

-- ── CPP's prices on the position snapshot ────────────────────────────────────
-- The snapshot used to be valued with Atlas's own NSE close, which guarantees the
-- book's weights disagree with the client's statement by design — a different price
-- source cannot produce the same number. CPP prices its own holdings; we copy that.
-- Nullable: rows synced before this column existed have no CPP price, and the reader
-- must show that rather than fall back to a second opinion.
ALTER TABLE atlas_foundation.maal_holding_snapshot
    ADD COLUMN IF NOT EXISTS cpp_price      numeric(18,4),
    ADD COLUMN IF NOT EXISTS cpp_value      numeric(18,2),
    ADD COLUMN IF NOT EXISTS cpp_weight_pct numeric(18,4);

-- ── Bonus shares can be recorded ─────────────────────────────────────────────
-- Bonus shares arrive at price 0, so portfolio_trades' price > 0 CHECK physically
-- refused them and the sync dropped them: two real BJ53 rows (AARTIDRUGS 84 on
-- 2020-10-05, CDSL 136 on 2024-08-24), 220 shares that CPP holds and Atlas's trade
-- log never explained the arrival of.
--
-- The CHECK is relaxed only for rows that SAY they are bonus, so the engine — which
-- never writes reason='bonus' — keeps the guard it has always had. A zero-price trade
-- from the engine is still a bug and still rejected.
ALTER TABLE atlas_foundation.portfolio_trades
    DROP CONSTRAINT IF EXISTS portfolio_trades_reason_check;
ALTER TABLE atlas_foundation.portfolio_trades
    ADD CONSTRAINT portfolio_trades_reason_check
    CHECK (reason = ANY (ARRAY['inception', 'signal', 'manual', 'stop', 'desk', 'bonus']));

ALTER TABLE atlas_foundation.portfolio_trades
    DROP CONSTRAINT IF EXISTS portfolio_trades_price_check;
ALTER TABLE atlas_foundation.portfolio_trades
    ADD CONSTRAINT portfolio_trades_price_check
    CHECK (price > 0 OR reason = 'bonus');
