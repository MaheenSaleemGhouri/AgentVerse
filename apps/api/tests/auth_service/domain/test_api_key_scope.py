"""`effective_role` is the whole of API-key authorization, so it is
tested exhaustively rather than by example: every (scope, role) pair.
"""

from __future__ import annotations

import pytest

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope, effective_role
from agentverse_api.auth_service.domain.role import Role


@pytest.mark.parametrize("member_role", list(Role))
def test_full_scope_never_exceeds_the_issuing_member(member_role: Role) -> None:
    assert effective_role(ApiKeyScope.FULL, member_role) is member_role


@pytest.mark.parametrize("member_role", list(Role))
def test_read_only_scope_caps_at_viewer(member_role: Role) -> None:
    assert effective_role(ApiKeyScope.READ_ONLY, member_role) is Role.VIEWER


@pytest.mark.parametrize("scope", list(ApiKeyScope))
@pytest.mark.parametrize("member_role", list(Role))
def test_a_key_never_grants_more_than_its_issuer_holds(
    scope: ApiKeyScope, member_role: Role
) -> None:
    from agentverse_api.auth_service.domain.role import satisfies

    assert satisfies(member_role, effective_role(scope, member_role))
