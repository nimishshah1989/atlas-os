#!/bin/bash
# Capture the recovery-critical box state that is NOT in git, into one archive.
# The code + schema are reproducible from git; this grabs the rest a rebuild needs:
#   .env (all creds — the single irreplaceable artifact), the crontab, the nginx site,
#   and a pm2 process dump. See docs/disaster-recovery.md.
#
# The archive CONTAINS SECRETS (.env). Copy it OFF-BOX to an encrypted store immediately;
# do not leave it lying on the box (that defeats the point) or commit it (it's gitignored
# by pattern, but be careful).
#
#   bash scripts/ops/backup_box_state.sh [dest_dir]      # default dest: /tmp
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-/tmp}"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp "$REPO/.env" "$WORK/env" 2>/dev/null || echo "  ! no .env found at $REPO/.env"
crontab -l > "$WORK/crontab.txt" 2>/dev/null || echo "  ! no crontab"
pm2 save >/dev/null 2>&1 && cp "$HOME/.pm2/dump.pm2" "$WORK/pm2_dump.pm2" 2>/dev/null || echo "  ! no pm2 dump"
for site in /etc/nginx/sites-enabled/atlas.jslwealth.in /etc/nginx/sites-available/atlas.jslwealth.in; do
  [ -e "$site" ] && cp "$site" "$WORK/nginx_atlas.conf" && break
done
git -C "$REPO" rev-parse HEAD > "$WORK/git_head.txt" 2>/dev/null || true

ARCHIVE="$DEST/atlas_box_state_$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$WORK" . && chmod 600 "$ARCHIVE"
echo "Wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
echo "CONTAINS SECRETS — copy it off-box to an encrypted store, then delete the local copy."
