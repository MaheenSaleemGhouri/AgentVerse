"""The one place a searchable `tsvector` expression is written.

A GIN index on an *expression* — rather than on a stored column — only
gets used when the query repeats that expression character for character.
Postgres will not tell you when it doesn't: it silently falls back to a
sequential scan, which is fast on a dev database with forty rows and a
production incident at four million.

So both sides are generated from here: the migration renders
`searchable(...)` into its `CREATE INDEX`, and every repository builds
its query through `search_query()`. They cannot drift, because there is
only one of them. The integration suite closes the loop by asserting
`EXPLAIN` picks a Bitmap Index Scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from agentverse_shared.search import TEXT_SEARCH_CONFIG, SearchMatch
from sqlalchemy import ColumnElement, Float, Row, Select, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnClause

#: What callers may pass as a column.
#:
#: Both arms are needed. Callers pass mapped attributes
#: (`AgentModel.name`), which are `InstrumentedAttribute` — and
#: SQLAlchemy's stubs do *not* make that a `ColumnElement` subtype, so a
#: `ColumnElement`-only signature would force a `# type: ignore` at every
#: call site. The union keeps the type error where it belongs: at the
#: boundary of this module, resolved once by `_element` below.
type SearchColumn[T] = InstrumentedAttribute[T] | ColumnElement[T]


def _element(column: SearchColumn[Any]) -> ColumnElement[Any]:
    """Narrow a caller's column to the type SQLAlchemy's own helpers want.

    `InstrumentedAttribute` *is* a column expression at runtime —
    `func.coalesce`, `select` and `.asc()` all accept it — but the stubs
    type those parameters as `ColumnElement`. One cast here, named and
    explained, in place of a scattering of suppressions at every use.
    """
    return cast("ColumnElement[Any]", column)


# `literal_column`, not `literal` — and this is load-bearing, not style.
#
# `literal("english")` compiles to a **bind parameter**. Postgres matches
# an expression index by comparing the parsed expression trees, and a
# parameter whose value it does not know at plan time does not match the
# constant the index was built with. The query runs, returns correct
# rows, and sequentially scans the table forever.
#
# `literal_column` renders the text inline, so the query says
# `to_tsvector('english', coalesce(name, '') || ' ' || ...)` — exactly
# what the migration wrote. These are module constants, never user
# input, so inlining them is not an injection surface; the *user's* query
# stays a bind parameter in `to_tsquery`.
_CONFIG: ColumnClause[str] = literal_column(f"'{TEXT_SEARCH_CONFIG}'")
_EMPTY: ColumnClause[str] = literal_column("''")
_SPACE: ColumnClause[str] = literal_column("' '")


def searchable(*columns: SearchColumn[str] | SearchColumn[str | None]) -> ColumnElement[TSVECTOR]:
    """`to_tsvector('english', coalesce(a,'') || ' ' || coalesce(b,''))`.

    `coalesce` is not optional: `NULL` anywhere in a concatenation makes
    the whole expression `NULL`, so an agent with no description would
    index as nothing and never be findable by its own name.

    Passing the configuration explicitly is what makes the expression
    immutable — and an expression index cannot be built on a
    non-immutable expression.
    """
    joined: ColumnElement[str] = func.coalesce(_element(columns[0]), _EMPTY)
    for column in columns[1:]:
        joined = joined.op("||")(_SPACE).op("||")(func.coalesce(_element(column), _EMPTY))
    return func.to_tsvector(_CONFIG, joined)


def rank(vector: ColumnElement[TSVECTOR], tsquery: str) -> ColumnElement[float]:
    """Cover-density rank of `vector` against a caller-built `tsquery`.

    `ts_rank_cd` rather than `ts_rank` because it weighs how close the
    matched terms fall to each other: for "sales qualifier", an entity
    whose name is that phrase should beat one that says "sales" in its
    name and "qualifier" forty words into its description.
    """
    return func.ts_rank_cd(vector, func.to_tsquery(_CONFIG, tsquery), type_=Float)


def matches(vector: ColumnElement[TSVECTOR], tsquery: str) -> ColumnElement[bool]:
    """The `@@` predicate — the part the GIN index actually serves."""
    return vector.op("@@")(func.to_tsquery(_CONFIG, tsquery))


def search_query(
    *,
    id_column: SearchColumn[str],
    title_column: SearchColumn[str],
    subtitle_column: SearchColumn[str | None],
    tsquery: str,
    where: Sequence[ColumnElement[bool]],
    limit: int,
) -> Select[tuple[str, str, str | None, float]]:
    """A ranked, limited search over one table.

    Every searchable context composes its query through here, differing
    only in its columns and its `where` — which is where `workspace_id`
    and `deleted_at IS NULL` belong. Tenant scoping is deliberately *not*
    baked in: this helper cannot know each table's tenant column, and a
    helper that silently half-scoped queries would be worse than one that
    makes each caller state it.

    Ties break on title so results are stable between identical calls —
    otherwise two equally-ranked agents would swap places between
    keystrokes, and the tests could not assert an order.
    """
    vector = searchable(title_column, subtitle_column)
    score = rank(vector, tsquery)
    title = _element(title_column)
    return cast(
        "Select[tuple[str, str, str | None, float]]",
        select(_element(id_column), title, _element(subtitle_column), score.label("rank"))
        .where(*where, matches(vector, tsquery))
        .order_by(score.desc(), title.asc())
        .limit(limit),
    )


def to_matches(rows: Sequence[Row[tuple[str, str, str | None, float]]]) -> list[SearchMatch]:
    """Map `search_query` output to the shared cross-context value type."""
    return [
        SearchMatch(id=row[0], title=row[1], subtitle=row[2], rank=float(row[3])) for row in rows
    ]
