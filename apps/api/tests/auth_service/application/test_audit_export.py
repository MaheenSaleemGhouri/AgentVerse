"""Unit tests for audit-log export serialisation.

Kept as direct calls on pure functions rather than through the HTTP
route: the interesting rules here are formula injection and stable
column order, and both are easier to state — and harder to accidentally
weaken — at this level.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest

from agentverse_api.auth_service.application.audit_export import CSV_COLUMNS, to_csv, to_json
from agentverse_api.auth_service.domain.entities import AuditLogEntry


def _entry(**overrides: object) -> AuditLogEntry:
    base = {
        "id": "entry-1",
        "workspace_id": "ws-1",
        "actor_user_id": "user-1",
        "action": "workspace.member_added",
        "target": "user-2",
        "outcome": "success",
        "metadata": {"role": "member"},
        "created_at": datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
        "organization_id": None,
    }
    base.update(overrides)
    return AuditLogEntry(**base)  # type: ignore[arg-type]


def _rows(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def test_csv_starts_with_the_declared_header_in_a_fixed_order() -> None:
    """The column order is part of the contract — someone's script
    parses it. A dataclass field reordering must not change it.
    """
    rows = _rows(to_csv([_entry()]))
    assert rows[0] == list(CSV_COLUMNS)


def test_csv_uses_rfc4180_line_endings() -> None:
    assert to_csv([_entry()]).endswith("\r\n")


@pytest.mark.parametrize("dangerous", ["=cmd|'/c calc'!A1", "+1+1", "-2+3", "@SUM(A1)"])
def test_a_value_that_would_be_a_spreadsheet_formula_is_neutralised(dangerous: str) -> None:
    """Audit values include user-controlled text. Exported to CSV and
    opened in a spreadsheet, a leading =/+/-/@ is a code-execution path
    (OWASP CSV injection), so it must not survive the export intact.
    """
    rows = _rows(to_csv([_entry(target=dangerous)]))
    target = rows[1][CSV_COLUMNS.index("target")]

    assert not target.startswith(("=", "+", "-", "@"))
    # Neutralised, not destroyed: prefixed so a spreadsheet treats it as
    # text, with the original still readable to a human reviewer.
    assert target == f"'{dangerous}"


def test_an_ordinary_value_is_not_mangled() -> None:
    rows = _rows(to_csv([_entry(target="user-2")]))
    assert rows[1][CSV_COLUMNS.index("target")] == "user-2"


def test_csv_renders_null_as_empty_and_metadata_as_compact_json() -> None:
    rows = _rows(to_csv([_entry(organization_id=None, metadata={"b": "2", "a": "1"})]))

    assert rows[1][CSV_COLUMNS.index("organization_id")] == ""
    # Sorted keys so two exports of the same data are byte-identical.
    assert rows[1][CSV_COLUMNS.index("metadata")] == '{"a":"1","b":"2"}'


def test_json_export_keeps_real_types_rather_than_stringifying_them() -> None:
    """CSV has to flatten everything to text; JSON does not, and forcing
    it to would make every consumer re-parse what JSON already expresses.
    """
    payload = json.loads(to_json([_entry(metadata={"role": "member"})]))

    assert payload[0]["metadata"] == {"role": "member"}
    assert payload[0]["organization_id"] is None
    assert payload[0]["created_at"] == "2026-08-03T12:30:00+00:00"


def test_exporting_nothing_still_produces_a_valid_document() -> None:
    """An empty workspace must download a header-only CSV and an empty
    JSON array, not a zero-byte file that looks like a failure.
    """
    assert _rows(to_csv([])) == [list(CSV_COLUMNS)]
    assert json.loads(to_json([])) == []
