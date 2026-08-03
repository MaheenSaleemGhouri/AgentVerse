"""Audit-log export serialisation.

Pure formatting, deliberately separated from the route: turning entries
into CSV or JSON has real correctness and safety rules (formula
injection, stable column order) that are worth testing directly rather
than through an HTTP client.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from datetime import date, datetime

from agentverse_api.auth_service.domain.entities import AuditLogEntry

#: Fixed column order. Not derived from the dataclass field order: a
#: field reordering must never silently change the shape of an export
#: someone else's tooling already parses.
CSV_COLUMNS = (
    "id",
    "created_at",
    "action",
    "outcome",
    "actor_user_id",
    "target",
    "workspace_id",
    "organization_id",
    "metadata",
)

#: A leading one of these makes a spreadsheet treat the cell as a
#: formula. Audit values include user-controlled text (targets, metadata),
#: so an exported log opened in Excel is a real code-execution path
#: unless the value is neutralised first (OWASP CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    if value and value.startswith(_FORMULA_PREFIXES):
        # Prefixed with an apostrophe, the conventional neutraliser:
        # the text stays readable and is no longer evaluated.
        return f"'{value}"
    return value


def _cell(entry: AuditLogEntry, column: str) -> str:
    if column == "metadata":
        # Compact JSON in one cell rather than exploded columns: metadata
        # keys vary per action, and a union of every key would produce a
        # mostly-empty sheet.
        return json.dumps(entry.metadata, sort_keys=True, separators=(",", ":"))
    value = getattr(entry, column)
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def to_csv(entries: Iterable[AuditLogEntry]) -> str:
    buffer = io.StringIO()
    # QUOTE_MINIMAL plus explicit \r\n: RFC 4180's line ending, which is
    # what spreadsheet software expects regardless of host platform.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for entry in entries:
        writer.writerow([_csv_safe(_cell(entry, column)) for column in CSV_COLUMNS])
    return buffer.getvalue()


def to_json(entries: Iterable[AuditLogEntry]) -> str:
    """JSON keeps the real types — `metadata` stays an object and nulls
    stay null. Flattening them to strings the way CSV must would force
    every consumer to re-parse what JSON can already express.
    """
    return json.dumps(
        [
            {
                "id": entry.id,
                "created_at": entry.created_at.isoformat(),
                "action": entry.action,
                "outcome": entry.outcome,
                "actor_user_id": entry.actor_user_id,
                "target": entry.target,
                "workspace_id": entry.workspace_id,
                "organization_id": entry.organization_id,
                "metadata": entry.metadata,
            }
            for entry in entries
        ],
        indent=2,
    )
