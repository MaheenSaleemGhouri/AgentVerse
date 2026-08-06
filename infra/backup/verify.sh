#!/usr/bin/env bash
#
# Prove the backup is a recovery plan rather than a hypothesis.
#
# Takes a backup of the source database, restores it into a scratch
# database, and asserts the restored copy actually contains the data.
# This is the only thing that makes `backup.sh` meaningful — a dump
# nobody has ever restored is a file, not a backup
# (`cloud-architect`: "an untested backup is a hypothesis").
#
# Run on a schedule, not just once. The failure this catches is drift:
# a new extension, a new table with a type the target lacks, a dump
# whose owner no longer exists. All of those appear months after the
# backup script was last touched, which is why "it worked when we wrote
# it" is not the bar.
#
# Usage:
#   DATABASE_URL=postgresql://... ./verify.sh
#
# The scratch database is created and dropped here. It is named
# distinctly so it cannot be confused with anything real.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRATCH_DB="${SCRATCH_DB:-agentverse_restore_check}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

PG_URL="${DATABASE_URL/+asyncpg/}"
# Everything up to the last `/` — the server, without the database name.
SERVER_URL="${PG_URL%/*}"
SCRATCH_URL="$SERVER_URL/$SCRATCH_DB"

cleanup() {
  psql "$SERVER_URL/postgres" -q -c "DROP DATABASE IF EXISTS $SCRATCH_DB" > /dev/null 2>&1 || true
}
# Dropped on any exit path, including failure: a scratch database left
# behind after a failed verification is the thing someone later mistakes
# for a real one.
trap cleanup EXIT

echo "== 1/4 Taking a backup"
BACKUP_DIR="$HERE/artifacts" "$HERE/backup.sh"
ARCHIVE="$(ls -t "$HERE/artifacts"/agentverse-*.dump | head -1)"

echo "== 2/4 Creating scratch database $SCRATCH_DB"
psql "$SERVER_URL/postgres" -q -c "DROP DATABASE IF EXISTS $SCRATCH_DB"
psql "$SERVER_URL/postgres" -q -c "CREATE DATABASE $SCRATCH_DB"

echo "== 3/4 Restoring into it"
RESTORE_URL="$SCRATCH_URL" \
  I_UNDERSTAND_THIS_IS_DESTRUCTIVE=yes \
  "$HERE/restore.sh" "$ARCHIVE"

echo "== 4/4 Asserting the restored copy has the data"

# Counting rows, not tables. A restore that recreated the schema and
# lost every row would pass a table-count check and fail the only thing
# anyone actually needs from a backup.
#
# `plans` specifically: it is seeded by migration, so a correctly
# restored database always has four rows. An empty `plans` means the
# restore produced a schema and no data — which is the exact failure a
# table-existence check would miss.
PLAN_COUNT="$(psql "$SCRATCH_URL" -tAc "SELECT count(*) FROM plans" 2>/dev/null || echo 0)"
if [[ "$PLAN_COUNT" -lt 4 ]]; then
  echo "FAILED: restored database has $PLAN_COUNT plans, expected at least 4." >&2
  echo "The backup restored a schema without its data — this is NOT a usable backup." >&2
  exit 1
fi

# Every table the platform cannot reconstruct. Listed explicitly rather
# than counted from the catalog, so a table that stops being backed up
# fails here instead of silently reducing the count by one.
for table in workspaces agents billing_subscriptions billing_credit_transactions billing_usage_events notifications; do
  if ! psql "$SCRATCH_URL" -tAc "SELECT 1 FROM $table LIMIT 1" > /dev/null 2>&1; then
    echo "FAILED: $table is missing from the restored database." >&2
    exit 1
  fi
done

echo
echo "PASS: $ARCHIVE restores into a working database."
echo "      $PLAN_COUNT plans present; every critical table restored."
