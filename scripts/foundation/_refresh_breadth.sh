#!/usr/bin/env bash
ENVFILE="/home/ubuntu/atlas-os/frontend/.env.local"
RAW=$(grep -E '^ATLAS_DB_URL=' "$ENVFILE" | head -1 | cut -d= -f2-)
RAW="${RAW%\"}"; RAW="${RAW#\"}"; RAW="${RAW%\'}"; RAW="${RAW#\'}"
PSQLURL="${RAW/+psycopg2/}"
echo "START $(date +%T)"
psql "$PSQLURL" -v ON_ERROR_STOP=1 -c "SET statement_timeout=0; REFRESH MATERIALIZED VIEW atlas.mv_sector_breadth;"
echo "EXIT=$? $(date +%T)"
psql "$PSQLURL" -c "select count(*) rows, max(as_of_date) m from atlas.mv_sector_breadth"
echo "BREADTH_REFRESH_DONE"
