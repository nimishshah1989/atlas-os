-- v6 Data Availability Check — Seed and Row Count Verification
--
-- Run via EC2 venv:
--   ssh jsl-wealth-server
--   cd atlas-os && source venv/bin/activate
--   psql "$ATLAS_DB_URL" -f scripts/v6_data_availability_check.sql > /tmp/v6_check_results.txt
--
-- Interpret results:
--   atlas_mf_switch_rules  0 → v6.0 BLOCKER: SWITCH page has no rules to display.
--                              Fix: run migrations/versions/094_v6_mf_switch_rules_seed.py
--                              (sensible defaults: Q3→Q1 same-category, ≥6mo consistency,
--                              expense-ratio tie-break). See docs/v6/data-source-map.md §Blockers.
--
--   atlas_ledger            0 → D.10 (realized outcomes per signal_call) has no source data.
--                              Not a launch blocker — page can show "no realized outcomes yet".
--
--   de_index_constituents  0 → B.2 benchmark weights cannot be derived. Blocker for BenchmarkToggle
--                              with accurate sector weight overlay.
--
--   atlas_universe_stocks   < 700 → Universe integrity issue. Expected ~727 rows (effective_to IS NULL).
--
--   atlas_fund_scorecard (top_holdings)  0 → B.3 fund holdings carousel empty.
--
--   atlas_scorecard_daily (features)     0 → conviction_tape will be all-NEUTRAL.
--                                          Fix: run atlas/features/scorecard_writer.py backfill.

SELECT 'atlas_mf_switch_rules' AS table_name, COUNT(*) AS row_count FROM atlas.atlas_mf_switch_rules;
SELECT 'atlas_ledger' AS table_name, COUNT(*) AS row_count FROM atlas.atlas_ledger;
SELECT 'de_index_constituents_nifty500' AS table_name, COUNT(*) AS row_count
  FROM public.de_index_constituents WHERE index_code = 'NIFTY500';
SELECT 'atlas_universe_stocks_active' AS table_name, COUNT(*) AS row_count
  FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL;
SELECT 'atlas_fund_scorecard_with_top_holdings' AS table_name, COUNT(*) AS row_count
  FROM atlas.atlas_fund_scorecard WHERE top_holdings IS NOT NULL;
SELECT 'atlas_scorecard_daily_with_features_latest' AS table_name, COUNT(*) AS row_count
  FROM atlas.atlas_scorecard_daily
  WHERE features IS NOT NULL
    AND date = (SELECT MAX(date) FROM atlas.atlas_scorecard_daily);

-- Bonus: confirm atlas_mf_switch_rules schema (rule_type, from_category, to_category)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'atlas'
  AND table_name = 'atlas_mf_switch_rules'
ORDER BY ordinal_position;
