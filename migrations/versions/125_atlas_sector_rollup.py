"""v4 D13 — atlas_sector_rollup: thin-tail sector fold (30+ raw → 22 actionable).

Tiny config table. The 8 thin-tail buckets (single-stock / <3-stock universes) fold
into their nearest parent before reaching the frontend, so every visible sector is
clickable with a peer set ≥ 3 deep. Fold map LOCKED in CONTEXT.md L962-973
(2026-05-26 post design-review). Consumers compute:

    canonical_sector = COALESCE(rollup.parent_sector_name, sector_name)

Applied live from EC2 via scripts/foundation/_db.exec_script (psycopg2 works here;
the Mac→MCP path in the MV migrations does not apply on the cloud box).

Revision ID: 125
Revises: 124
Create Date: 2026-06-25 IST
"""

from __future__ import annotations

from alembic import op

revision = "125"
down_revision = "124"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE IF NOT EXISTS atlas.atlas_sector_rollup (
  sector_name         varchar(64) PRIMARY KEY,
  parent_sector_name  varchar(64) NOT NULL,
  note                text,
  created_at          timestamptz NOT NULL DEFAULT now()
);
"""

# Locked fold map — CONTEXT.md L962-973. 8 thin-tail buckets → 4 parents.
_SEED = """
INSERT INTO atlas.atlas_sector_rollup (sector_name, parent_sector_name, note) VALUES
  ('Diamond, Jewellery & Precious Metals', 'Consumer Discretionary', 'D13 thin-tail fold'),
  ('Hospitality',                          'Consumer Discretionary', 'D13 thin-tail fold'),
  ('Media & Entertainment',                'Communication Services', 'D13 thin-tail fold'),
  ('Printing & Publishing',                'Communication Services', 'D13 thin-tail fold'),
  ('Aquaculture',                          'Consumer Staples',       'D13 thin-tail fold'),
  ('Tea & Coffee',                         'Consumer Staples',       'D13 thin-tail fold'),
  ('Fertilisers & Agrochemicals',          'Materials',              'D13 thin-tail fold'),
  ('Paper Products',                       'Materials',              'D13 thin-tail fold')
ON CONFLICT (sector_name) DO UPDATE
  SET parent_sector_name = EXCLUDED.parent_sector_name,
      note               = EXCLUDED.note;
"""

_DROP = "DROP TABLE IF EXISTS atlas.atlas_sector_rollup CASCADE;"


def upgrade() -> None:
    op.execute(_CREATE)
    op.execute(_SEED)


def downgrade() -> None:
    op.execute(_DROP)
