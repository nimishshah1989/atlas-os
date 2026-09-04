-- 03_classification.sql — atlas_global taxonomy + ETF classification (the moat).
-- Tables: country, taxonomy_sector, taxonomy_geo, taxonomy_role, etf_classification,
--         etf_classification_override, classification_validation_log.
-- Plan: "Schema `atlas_global` — core tables" (Taxonomy, etf_classification, overrides, log) and
--       "Classification engine" (dimensions, layers L2/L3, validation, human loop).
-- Requires 00_core.sql. Idempotent; no DROP; no function bodies.
-- Taxonomy rows are seeded from docs/global/taxonomy.md (FM-reviewed, versioned) in Phase 2 —
-- nothing here carries data.

-- country — ISO-3166 alpha-2 reference; msci_class drives the country-basket product line.
CREATE TABLE IF NOT EXISTS atlas_global.country (
    iso2        char(2)     NOT NULL,
    name        text        NOT NULL,
    region      text,                                       -- north_america | europe | asia_pacific | latam | mea | …
    msci_class  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT country_pkey PRIMARY KEY (iso2),
    CONSTRAINT chk_country_msci_class
        CHECK (msci_class IS NULL OR msci_class IN ('developed', 'emerging', 'frontier', 'standalone'))
);

-- taxonomy_sector — level 1 = GICS 11, level 2 = sub-sector (energy_renewable_solar,
-- energy_midstream_transmission, energy_nuclear_uranium, utilities_grid, …), level 3 = theme.
CREATE TABLE IF NOT EXISTS atlas_global.taxonomy_sector (
    id           text        NOT NULL,                      -- slug, e.g. energy_renewable_solar
    level        smallint    NOT NULL,
    parent_id    text        REFERENCES atlas_global.taxonomy_sector (id),
    name         text        NOT NULL,
    gics_code    text,                                      -- level 1 only
    description  text,
    version      integer     NOT NULL DEFAULT 1,            -- taxonomy version that introduced the row
    is_active    boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT taxonomy_sector_pkey PRIMARY KEY (id),
    CONSTRAINT chk_taxonomy_sector_level CHECK (level IN (1, 2, 3)),
    CONSTRAINT chk_taxonomy_sector_parent CHECK (level = 1 OR parent_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_taxonomy_sector_parent
    ON atlas_global.taxonomy_sector (parent_id);

-- taxonomy_geo — country | region | global nodes with the ISO → region roll-up.
CREATE TABLE IF NOT EXISTS atlas_global.taxonomy_geo (
    id           text        NOT NULL,                      -- 'JP', 'asia_ex_japan', 'global', …
    kind         text        NOT NULL,
    iso2         char(2)     REFERENCES atlas_global.country (iso2),   -- set for kind = 'country'
    region       text,                                      -- roll-up target for countries; self for regions
    name         text        NOT NULL,
    version      integer     NOT NULL DEFAULT 1,
    is_active    boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT taxonomy_geo_pkey PRIMARY KEY (id),
    CONSTRAINT chk_taxonomy_geo_kind CHECK (kind IN ('country', 'region', 'global')),
    CONSTRAINT chk_taxonomy_geo_iso2 CHECK (kind <> 'country' OR iso2 IS NOT NULL)
);

-- taxonomy_role — pure_play | picks_and_shovels | diversified | not_applicable.
CREATE TABLE IF NOT EXISTS atlas_global.taxonomy_role (
    id           text        NOT NULL,
    name         text        NOT NULL,
    description  text,
    is_active    boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT taxonomy_role_pkey PRIMARY KEY (id),
    CONSTRAINT chk_taxonomy_role_id
        CHECK (id IN ('pure_play', 'picks_and_shovels', 'diversified', 'not_applicable'))
);

-- etf_classification — one row per (instrument, version); the current row has valid_to IS NULL.
-- Structure flags come from L2 rules (rules win over the LLM); sector/geo/role/themes may come
-- from rules, the LLM, or a human. status = auto | review | confirmed | override; the board and
-- baskets read confirmed | auto only. asset_class and strategy are the two peer-group axes
-- (deciles are within asset class × strategy) — the plan lists them under "Dimensions per ETF".
CREATE TABLE IF NOT EXISTS atlas_global.etf_classification (
    instrument_id     uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    version           integer       NOT NULL,
    asset_class       text,
    strategy          text,
    sector_id         text          REFERENCES atlas_global.taxonomy_sector (id),
    sub_sector_id     text          REFERENCES atlas_global.taxonomy_sector (id),
    theme_ids         text[]        NOT NULL DEFAULT '{}',  -- ≤ 3 taxonomy_sector level-3 ids
    geo_focus_type    text,
    country_codes     text[]        NOT NULL DEFAULT '{}',  -- ISO2 list
    country_pure      boolean,
    role_id           text          REFERENCES atlas_global.taxonomy_role (id),
    leveraged         boolean,
    inverse           boolean,
    hedged            boolean,
    active            boolean,
    basket_eligible   boolean       NOT NULL DEFAULT false, -- ¬leveraged ∧ ¬inverse ∧ fractionable ∧ adv ≥ floor ∧ aum ≥ floor
    confidence        numeric(5,4),
    rationale         text,                                 -- ≤ 60 words, from the LLM or the human
    evidence          jsonb,                                -- cited holdings / tickers
    classified_by     text          NOT NULL,               -- rules | llm:<model> | human:<email>
    status            text          NOT NULL,
    taxonomy_version  integer,
    valid_from        date          NOT NULL,
    valid_to          date,
    created_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_classification_pkey PRIMARY KEY (instrument_id, version),
    CONSTRAINT chk_etf_classification_asset_class
        CHECK (asset_class IS NULL OR asset_class IN
               ('equity', 'fixed_income', 'commodity', 'currency', 'multi_asset', 'alternative')),
    CONSTRAINT chk_etf_classification_strategy
        CHECK (strategy IS NULL OR strategy IN
               ('broad', 'factor', 'sector', 'thematic', 'country', 'commodity', 'bond_duration', 'leveraged')),
    CONSTRAINT chk_etf_classification_geo_focus
        CHECK (geo_focus_type IS NULL OR geo_focus_type IN ('single_country', 'region', 'global')),
    CONSTRAINT chk_etf_classification_status
        CHECK (status IN ('auto', 'review', 'confirmed', 'override')),
    CONSTRAINT chk_etf_classification_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);
CREATE INDEX IF NOT EXISTS ix_etf_classification_current
    ON atlas_global.etf_classification (instrument_id, valid_to);
CREATE INDEX IF NOT EXISTS ix_etf_classification_status
    ON atlas_global.etf_classification (status);
CREATE INDEX IF NOT EXISTS ix_etf_classification_sector
    ON atlas_global.etf_classification (sector_id, sub_sector_id);
CREATE INDEX IF NOT EXISTS ix_etf_classification_geo
    ON atlas_global.etf_classification (geo_focus_type);

-- etf_classification_override — per-field sticky human overrides, re-applied on every run.
-- History is kept (set_at in the key); readers take the latest is_active row per field.
CREATE TABLE IF NOT EXISTS atlas_global.etf_classification_override (
    instrument_id  uuid        NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    field          text        NOT NULL,                    -- an etf_classification column name
    value          jsonb       NOT NULL,                    -- typed per field (text / bool / text[])
    set_by         text        NOT NULL,                    -- app_user.email
    reason         text,
    set_at         timestamptz NOT NULL DEFAULT now(),
    is_active      boolean     NOT NULL DEFAULT true,
    CONSTRAINT etf_classification_override_pkey PRIMARY KEY (instrument_id, field, set_at)
);
CREATE INDEX IF NOT EXISTS ix_etf_classification_override_active
    ON atlas_global.etf_classification_override (instrument_id, is_active);

-- classification_validation_log — every validate.py failure (factuality-guard pattern):
-- ids ∉ taxonomy, evidence ⊄ holdings, single_country disagrees with L1, flags ≠ rules, …
CREATE TABLE IF NOT EXISTS atlas_global.classification_validation_log (
    id             bigserial   NOT NULL,
    instrument_id  uuid        REFERENCES atlas_global.instrument_master (instrument_id),
    run_at         timestamptz NOT NULL DEFAULT now(),
    rule           text        NOT NULL,
    detail         jsonb,
    CONSTRAINT classification_validation_log_pkey PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_classification_validation_log_instrument
    ON atlas_global.classification_validation_log (instrument_id, run_at);
