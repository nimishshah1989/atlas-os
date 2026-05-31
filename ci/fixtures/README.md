# CI fixtures

## `external_de_tables.sql`

Schema-only (`CREATE TABLE` + indexes, **no data, no credentials**) for the
`de_*` tables owned by the **separate data-engineering pipeline**, not by atlas
migrations. atlas migrations build materialized views and indexes that *read*
these tables (e.g. migration 100/101/122 `... FROM public.de_index_prices`,
migration 110 `CREATE INDEX ... ON de_equity_ohlcv`), so a fresh CI database
must have their (empty) schema in place **before** `alembic upgrade head`.

This is the "captured schema-only dump" approach (chosen 2026-05-31): the real
prod structure, so no column can be wrong by hand; CI never needs live prod
access (the structure is committed here); and it only needs regenerating when
the DE pipeline changes one of these tables (rare).

### Regenerate (run on EC2 — the Mac stalls on the pooler)

Prod is Supabase **Postgres 17**, but EC2's native `pg_dump` is 16.x and refuses
on a version mismatch — so dump with a PG17 client via Docker (already on EC2;
it's what `make backup` uses):

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214
cd /home/ubuntu/atlas-os
set -a && . ./.env && set +a
# Convert the SQLAlchemy URL (postgresql+psycopg2://…) to a libpq URL:
PSQL_URL=$(printf '%s' "$ATLAS_DB_URL" | sed -E 's#^postgresql\+psycopg2#postgresql#')
docker run --rm postgres:17 pg_dump "$PSQL_URL" \
  --schema-only --no-owner --no-privileges --no-comments \
  -t 'public.de_*' \
  | python3 ci/fixtures/slim_de_dump.py > ci/fixtures/external_de_tables.sql
```

(Run the `python3 …slim_de_dump.py` part wherever the repo is checked out; the
`pg_dump` part must run where it can reach the DB.) `-t 'public.de_*'` captures
every `de_*` table on prod; the raw dump also carries partition children, RLS
policies, FK constraints and sequences that a clean CI DB doesn't need (and that
would fail there), so **`slim_de_dump.py` reduces it to the bare parent tables**
— that script's docstring explains exactly what it keeps. Commit the slimmed
`external_de_tables.sql`. The CI Postgres service is pinned to `postgres:17` to
match prod (17.6).

If `alembic upgrade head` ever fails in CI on a *non*-`de_` missing relation,
that table is another external dependency — add it to the dump pattern and
regenerate.
