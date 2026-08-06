#!/usr/bin/env bash
#
# Postgres backup for AgentVerse.
#
# `cloud-architect`'s standing rule: an untested backup is a hypothesis,
# not a recovery plan. So this script's companion, `restore.sh`, is not
# optional documentation — `verify.sh` runs both against a scratch
# database and is the only thing that turns this file into a backup.
#
# Scope, stated plainly: this covers **Postgres**, which is AgentVerse's
# system of record and holds everything that cannot be reconstructed —
# workspaces, agents, subscriptions, the credit ledger, usage events.
#
# Deliberately NOT covered, because each is reconstructible or lives
# elsewhere:
#   - Redis: cache, queue and rate-limit counters. Rule 13 makes
#     everything in it reconstructable from Postgres or safely losable,
#     so backing it up would create a second copy of state we have
#     already decided is disposable.
#   - Stripe: the payment provider is the system of record for
#     payment-method and invoice facts. Our tables are a projection, and
#     `ReconciliationService` is how they are repaired — not a restore.
#   - Uploaded documents (`document_storage_root`): object storage, whose
#     own lifecycle policy owns them. Named here so their absence is a
#     decision rather than an oversight.
#
# Usage:
#   ./backup.sh                      # writes to ./artifacts
#   BACKUP_DIR=/mnt/backups ./backup.sh
#
# Requires DATABASE_URL (libpq form, not SQLAlchemy's `+asyncpg`).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$(dirname "$0")/artifacts}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required (libpq form: postgresql://user:pass@host:port/db)" >&2
  exit 1
fi

# `+asyncpg` is SQLAlchemy's driver marker and pg_dump does not
# understand it. Stripped rather than required-in-a-different-shape, so
# the same value works for the app and for this script.
PG_URL="${DATABASE_URL/+asyncpg/}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/agentverse-$STAMP.dump"

echo "Backing up to $ARCHIVE"

# `--format=custom` rather than plain SQL: it is compressed, and it lets
# `pg_restore` do a selective or parallel restore, which is what turns a
# multi-gigabyte recovery from hours into minutes.
#
# `--no-owner --no-privileges`: the restore target's roles differ from
# production's, and a dump that insists on production's owner fails to
# restore anywhere else — including the verification run below, which is
# exactly the scenario that must work.
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --verbose \
  --file="$ARCHIVE" \
  "$PG_URL" 2>&1 | tail -5

# A dump that pg_restore cannot list is a corrupt file that looks like a
# backup. Checked here rather than at restore time, when it is too late.
if ! pg_restore --list "$ARCHIVE" > /dev/null 2>&1; then
  echo "FAILED: the archive is not readable by pg_restore — treating as no backup" >&2
  rm -f "$ARCHIVE"
  exit 1
fi

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
TABLES="$(pg_restore --list "$ARCHIVE" | grep -c 'TABLE DATA' || true)"
echo "OK: $ARCHIVE ($SIZE, $TABLES tables with data)"

# Retention. Runs *after* the new backup is verified readable, so a
# failed backup never deletes the last good one.
find "$BACKUP_DIR" -name 'agentverse-*.dump' -type f -mtime "+$RETENTION_DAYS" -print -delete
