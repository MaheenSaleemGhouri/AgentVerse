#!/usr/bin/env bash
#
# Restore an AgentVerse Postgres backup.
#
# Exists as a script rather than as instructions in a runbook because a
# restore happens under incident pressure, and a procedure typed from
# memory at 3am is where an outage becomes a data-loss event.
#
# Usage:
#   RESTORE_URL=postgresql://... ./restore.sh artifacts/agentverse-….dump
#
# `RESTORE_URL` is deliberately a *different* variable from
# `DATABASE_URL`. Pointing a restore at the production database by
# reusing the same variable the app already has exported is the single
# most destructive mistake available here, and requiring a separate,
# explicitly-set value makes it a decision rather than an accident.

set -euo pipefail

ARCHIVE="${1:-}"

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "Usage: RESTORE_URL=postgresql://... $0 <archive.dump>" >&2
  exit 1
fi

if [[ -z "${RESTORE_URL:-}" ]]; then
  echo "RESTORE_URL is required. It is deliberately not DATABASE_URL:" >&2
  echo "  restoring over the live database must be an explicit choice." >&2
  exit 1
fi

PG_URL="${RESTORE_URL/+asyncpg/}"

# A restore is destructive by nature — `--clean` drops what it replaces.
# The guard is opt-in confirmation, not a prompt: this runs in CI and in
# scripts, and an interactive prompt would either block them or be
# answered blindly.
if [[ "${I_UNDERSTAND_THIS_IS_DESTRUCTIVE:-}" != "yes" ]]; then
  echo "Refusing to restore over $PG_URL" >&2
  echo "Set I_UNDERSTAND_THIS_IS_DESTRUCTIVE=yes to proceed." >&2
  exit 1
fi

echo "Restoring $ARCHIVE"

# `--clean --if-exists` so the target does not have to be empty, and
# `--no-owner --no-privileges` because the target's roles are not
# production's.
#
# `--exit-on-error` is deliberately NOT set: a restore into a database
# with slightly different extensions emits harmless errors on objects
# that already exist, and aborting on the first would leave a
# half-restored database — worse than finishing and reporting.
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname="$PG_URL" \
  "$ARCHIVE" 2>&1 | tail -20 || true

echo "Restore finished. Verify before trusting it:"
echo "  psql \"$PG_URL\" -c 'SELECT count(*) FROM workspaces'"
