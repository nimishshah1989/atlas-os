-- "Monday confirmations" -> "MaaL Process" (Multi Asset Alpha - Leaders).
--
-- Also aligns the three portfolio codes to CPP's own vocabulary so there is no
-- translation table between the two systems: alpha -> leaders, india_xi -> ind11.
--
-- Applied via: python3 -c "import _db; _db.exec_script(open('maal_rename.sql').read())"
--
-- Safe to run once. RENAME preserves every published report intact — the three
-- circulated reports keep rendering exactly as they were published.

-- ORDER MATTERS. The old CHECK still enumerates ('alpha','passive','india_xi'), so it
-- must be dropped BEFORE the value updates — otherwise UPDATE ... = 'leaders' violates
-- the very constraint being replaced. Learned the hard way: the whole script rolled
-- back on that violation, which is exactly what a single transaction is for.
ALTER TABLE atlas_foundation.mpf_confirmation
    DROP CONSTRAINT IF EXISTS mpf_confirmation_portfolio_code_check;

ALTER TABLE atlas_foundation.mpf_confirmation RENAME TO maal_confirmation;
ALTER TABLE atlas_foundation.mpf_call         RENAME TO maal_call;
ALTER TABLE atlas_foundation.mpf_evidence     RENAME TO maal_evidence;

ALTER TABLE atlas_foundation.maal_confirmation RENAME COLUMN portfolio_code TO maal_code;

UPDATE atlas_foundation.maal_confirmation SET maal_code = 'leaders' WHERE maal_code = 'alpha';
UPDATE atlas_foundation.maal_confirmation SET maal_code = 'ind11'   WHERE maal_code = 'india_xi';

ALTER TABLE atlas_foundation.maal_confirmation
    ADD CONSTRAINT maal_confirmation_code_check
    CHECK (maal_code IN ('leaders', 'passive', 'ind11'));

-- The cap thresholds keep their meaning; only their keys move.
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.leaders' WHERE threshold_key = 'mpf_max_cap.alpha';
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.passive' WHERE threshold_key = 'mpf_max_cap.passive';
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.ind11' WHERE threshold_key = 'mpf_max_cap.india_xi';
