"""Shared SQLAlchemy declarative base.

One `Base` for the whole service so every bounded context's ORM models
(starting with `auth_service`) register into the same metadata object —
what Alembic's autogenerate diffs against (CLAUDE.md §8: Alembic only).
"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Every `Mapped[datetime]` column becomes TIMESTAMPTZ, not a naive
    # TIMESTAMP, without repeating `mapped_column(DateTime(timezone=True))`
    # on every field — CLAUDE.md §8: "timestamps `*_at` as `timestamptz`
    # in UTC."
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }
