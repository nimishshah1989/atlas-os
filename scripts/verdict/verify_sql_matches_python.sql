-- verify_sql_matches_python.sql
-- Smoke test: 5 representative cases comparing atlas.derive_verdict() SQL function
-- against the Python atlas.verdict.derive.derive_verdict() module.
--
-- Run on Supabase project nanvgbhootvvthjujkvs to verify parity.
-- All 5 cases must return result = 'PASS'.
--
-- Python equivalents (from tests/verdict/test_derive.py):
--   case_1  → test_positive_cell_stage2_all_gates_pass_not_owned_returns_BUY
--   case_2  → test_positive_cell_stage4_returns_WAIT
--   case_3  → test_positive_cell_risk_gate_fail_returns_WAIT
--   case_4  → test_positive_cell_stage3_not_owned_returns_WATCH
--   case_5  → test_negative_cell_owned_returns_SELL
--
-- Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4
-- Spec locks: Q1 (Stage 3 → WATCH/HOLD never WAIT), Q5 (Micro exempt from Weinstein veto)

SELECT
  'case_1_BUY_clean' AS test_case,
  v.verdict,
  v.reason,
  CASE WHEN v.verdict = 'BUY' AND v.reason IS NULL THEN 'PASS' ELSE 'FAIL' END AS result
FROM atlas.derive_verdict('POSITIVE', 2, false, 'Large', true, true, true, true, true) v

UNION ALL

SELECT
  'case_2_WAIT_stage4' AS test_case,
  v.verdict,
  v.reason,
  CASE WHEN v.verdict = 'WAIT' AND v.reason = 'Stage 4 vetoes positive cell' THEN 'PASS' ELSE 'FAIL' END AS result
FROM atlas.derive_verdict('POSITIVE', 4, false, 'Large', true, true, true, true, true) v

UNION ALL

SELECT
  'case_3_WAIT_risk_gate_fail' AS test_case,
  v.verdict,
  v.reason,
  CASE WHEN v.verdict = 'WAIT' AND v.reason = 'Risk gate fail' THEN 'PASS' ELSE 'FAIL' END AS result
FROM atlas.derive_verdict('POSITIVE', 2, false, 'Large', true, true, false, true, true) v

UNION ALL

SELECT
  'case_4_WATCH_stage3' AS test_case,
  v.verdict,
  v.reason,
  CASE WHEN v.verdict = 'WATCH' AND v.reason = 'Stage 3 topping' THEN 'PASS' ELSE 'FAIL' END AS result
FROM atlas.derive_verdict('POSITIVE', 3, false, 'Large', true, true, true, true, true) v

UNION ALL

SELECT
  'case_5_SELL_owned' AS test_case,
  v.verdict,
  v.reason,
  CASE WHEN v.verdict = 'SELL' AND v.reason IS NULL THEN 'PASS' ELSE 'FAIL' END AS result
FROM atlas.derive_verdict('NEGATIVE', 4, true, 'Large', true, true, true, true, true) v

ORDER BY test_case;

-- Expected output (all PASS):
-- case_1_BUY_clean           | BUY         | null                        | PASS
-- case_2_WAIT_stage4         | WAIT        | Stage 4 vetoes positive cell | PASS
-- case_3_WAIT_risk_gate_fail | WAIT        | Risk gate fail               | PASS
-- case_4_WATCH_stage3        | WATCH       | Stage 3 topping              | PASS
-- case_5_SELL_owned          | SELL        | null                        | PASS
