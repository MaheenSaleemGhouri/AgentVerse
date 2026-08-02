"""What an invitation grants membership in — mirrors `api_key_scope.py`'s
minimal standalone-`StrEnum` pattern.
"""

from __future__ import annotations

from enum import StrEnum


class InvitationTargetType(StrEnum):
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
