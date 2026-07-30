-- Monday confirmations: the FM's weekly buy/sell document per model portfolio.
-- Applied via: python3 -c "import _db; _db.exec_script(open('mpf_ddl.sql').read())"
--
-- The book is NOT re-derived at read time. Publishing folds the calls onto the
-- previous published book and stores the result on the row (resulting_book), so
-- a report renders forever exactly as it was published.
--
-- Drafts are deliberately unconstrained (a half-typed row must be saveable on a
-- Friday); publish-time validation lives in frontend/src/lib/confirmations.ts.

CREATE TABLE IF NOT EXISTS atlas_foundation.mpf_confirmation (
    confirmation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_code  text NOT NULL CHECK (portfolio_code IN ('alpha', 'passive', 'india_xi')),
    week_of         date NOT NULL,
    status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    resulting_book  jsonb,
    published_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (portfolio_code, week_of),
    CHECK (status = 'draft' OR resulting_book IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_mpf_confirmation_book
    ON atlas_foundation.mpf_confirmation (portfolio_code, status, week_of DESC);

-- UNIQUE(confirmation_id, instrument_key) IS the "same name cannot be on both
-- the buy and the sell side" rule — enforced by the database, not the form.
CREATE TABLE IF NOT EXISTS atlas_foundation.mpf_call (
    call_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confirmation_id bigint NOT NULL
                    REFERENCES atlas_foundation.mpf_confirmation(confirmation_id) ON DELETE CASCADE,
    side            text NOT NULL CHECK (side IN ('buy', 'sell')),
    instrument_key  text NOT NULL,
    symbol          text NOT NULL,
    name            text NOT NULL DEFAULT '',
    sector          text,
    weight_pct      numeric(6,2) NOT NULL DEFAULT 0,
    trigger_price   numeric(18,4),
    stop_price      numeric(18,4),
    reasons         text[] NOT NULL DEFAULT '{}',
    comment         text NOT NULL DEFAULT '',
    chart_image     bytea,
    chart_mime      text,
    position        integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (confirmation_id, instrument_key)
);

CREATE INDEX IF NOT EXISTS ix_mpf_call_confirmation
    ON atlas_foundation.mpf_call (confirmation_id, side, position);

-- "Additional weight of evidence": the 4-5 free sections under the calls.
CREATE TABLE IF NOT EXISTS atlas_foundation.mpf_evidence (
    evidence_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confirmation_id bigint NOT NULL
                    REFERENCES atlas_foundation.mpf_confirmation(confirmation_id) ON DELETE CASCADE,
    position        integer NOT NULL DEFAULT 0,
    title           text NOT NULL DEFAULT '',
    comment         text NOT NULL DEFAULT '',
    image           bytea,
    mime            text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mpf_evidence_confirmation
    ON atlas_foundation.mpf_evidence (confirmation_id, position);

-- Per-portfolio max position cap (FM, 2026-07-30). Drives the sell-side pre-fill:
-- any holding at, above, or within 1% of the cap can only come down, so it is a
-- standing sell candidate. 0 = no cap set for that book yet → nothing pre-fills.
-- Lives in atlas_thresholds so it stays editable from /admin/thresholds (rule #4);
-- the confirmations tab edits the same rows inline.
INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units,
     min_allowed, max_allowed, default_value, is_active)
SELECT k, 0, 'portfolio', d, 'percent', 0, 100, 0, TRUE
FROM (VALUES
    ('mpf_max_cap.alpha',    'Multi Asset Alpha — max position cap % (0 = unset)'),
    ('mpf_max_cap.passive',  'Passive — max position cap % (0 = unset)'),
    ('mpf_max_cap.india_xi', 'India XI — max position cap % (0 = unset)')
) AS v(k, d)
WHERE NOT EXISTS (
    SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = v.k
);
