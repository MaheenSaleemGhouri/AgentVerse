"""phase 12: audit_logs immutability trigger

Revision ID: 9011ed21fa17
Revises: 7c2a4e91f3b6
Create Date: 2026-08-19

`audit_logs` has been insert-only *by convention* since Phase 1 — every
call site goes through `AuditService.record()`, which has no update or
delete method — but nothing at the database level actually stopped an
UPDATE or DELETE against the table. A Phase 12 SOC 2 readiness review
flagged this as a real gap against "immutable audit log."

A `BEFORE UPDATE OR DELETE` trigger that raises, rather than a `REVOKE`
on the application's Postgres role: this repo's migrations have never
had to know the name of that role (it differs across local/CI/staging/
production connection strings), and a trigger enforces the same
guarantee regardless of which role issues the statement — including the
application's own role, so a future bug (not just a malicious actor)
can't silently rewrite history either.

DELETE is blocked unconditionally — no legitimate operation ever
removes an audit_logs row (every FK *from* another table's rows *into*
audit_logs doesn't exist; the FKs run the other way, audit_logs
referencing `workspaces`/`users`/`organizations`, each `ON DELETE SET
NULL`). That `SET NULL` action is itself implemented as an UPDATE, and
is the one legitimate mutation this table needs to keep allowing —
deleting a workspace/user/organization must not be blocked just because
its audit trail references it. So UPDATE is only blocked when it
changes anything *other than* nulling `workspace_id`, `actor_user_id`,
or `organization_id`: the row's actual content (`action`, `outcome`,
`target`, `metadata`, `created_at`) can never change, but a dangling
reference can still be nulled out from under a deleted parent row.
"""

from typing import Union
from collections.abc import Sequence

from alembic import op

revision: str = "9011ed21fa17"
down_revision: Union[str, None] = "7c2a4e91f3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_audit_log_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'audit_logs is append-only: DELETE is not permitted';
            END IF;

            -- TG_OP = 'UPDATE' from here. Allow only an FK ON DELETE SET
            -- NULL cascade nulling one of the three reference columns —
            -- every other column, including a reference column changing
            -- to anything other than NULL, is rejected.
            IF NEW.action IS DISTINCT FROM OLD.action
                OR NEW.outcome IS DISTINCT FROM OLD.outcome
                OR NEW.target IS DISTINCT FROM OLD.target
                OR NEW.metadata IS DISTINCT FROM OLD.metadata
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR NEW.id IS DISTINCT FROM OLD.id
                OR (NEW.workspace_id IS DISTINCT FROM OLD.workspace_id AND NEW.workspace_id IS NOT NULL)
                OR (NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id AND NEW.actor_user_id IS NOT NULL)
                OR (NEW.organization_id IS DISTINCT FROM OLD.organization_id AND NEW.organization_id IS NOT NULL)
            THEN
                RAISE EXCEPTION 'audit_logs is append-only: only a referenced row being deleted may null workspace_id/actor_user_id/organization_id';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
