"""The permission matrix and the widened hierarchy.

Pure-function tests: no HTTP, no database. The matrix is the single
canonical source `authorization-expert` requires, so its properties are
asserted structurally rather than by spot-checking a handful of pairs.
"""

from __future__ import annotations

import pytest

from agentverse_api.auth_service.domain.permission import (
    Permission,
    has_permission,
    permissions_for,
)
from agentverse_api.auth_service.domain.role import LEGACY_ROLES, Role, rank, satisfies


class TestHierarchyIsBackwardCompatible:
    """The four original roles must keep their exact relative meaning."""

    def test_legacy_order_is_preserved(self) -> None:
        assert rank(Role.OWNER) > rank(Role.ADMIN)
        assert rank(Role.ADMIN) > rank(Role.MEMBER)
        assert rank(Role.MEMBER) > rank(Role.VIEWER)

    def test_new_roles_sit_between_admin_and_member(self) -> None:
        # This is the property that makes the change additive: nothing
        # new reaches admin, and everything new outranks member.
        for role in (Role.MANAGER, Role.DEVELOPER, Role.ANALYST):
            assert rank(role) < rank(Role.ADMIN)
            assert rank(role) > rank(Role.MEMBER)

    def test_admin_floor_still_admits_only_admin_and_owner(self) -> None:
        admitted = {role for role in Role if satisfies(role, Role.ADMIN)}
        assert admitted == {Role.OWNER, Role.ADMIN}

    def test_member_floor_now_admits_the_three_new_roles(self) -> None:
        admitted = {role for role in Role if satisfies(role, Role.MEMBER)}
        assert admitted == {
            Role.OWNER,
            Role.ADMIN,
            Role.MANAGER,
            Role.DEVELOPER,
            Role.ANALYST,
            Role.MEMBER,
        }
        assert Role.VIEWER not in admitted

    def test_legacy_roles_constant_matches_the_original_four(self) -> None:
        expected = {Role.OWNER, Role.ADMIN, Role.MEMBER, Role.VIEWER}
        assert expected == LEGACY_ROLES


class TestInheritance:
    def test_every_role_is_a_superset_of_every_lower_role(self) -> None:
        """The documented-superset guarantee, asserted for all 21 pairs."""
        for higher in Role:
            for lower in Role:
                if rank(higher) > rank(lower):
                    assert permissions_for(lower) <= permissions_for(higher), (
                        f"{higher} does not inherit everything {lower} has"
                    )

    def test_owner_holds_every_permission(self) -> None:
        assert permissions_for(Role.OWNER) == frozenset(Permission)

    def test_viewer_holds_no_write_permission(self) -> None:
        viewer = permissions_for(Role.VIEWER)
        assert all(p.value.endswith(":view") for p in viewer)


class TestSpecificGrants:
    @pytest.mark.parametrize(
        ("role", "permission", "expected"),
        [
            # An analyst reads the compliance surfaces...
            (Role.ANALYST, Permission.AUDIT_LOG_EXPORT, True),
            (Role.ANALYST, Permission.ANALYTICS_VIEW, True),
            # ...but gains no authoring or governance power.
            (Role.ANALYST, Permission.AGENT_DELETE, False),
            (Role.ANALYST, Permission.MEMBER_INVITE, False),
            (Role.ANALYST, Permission.BILLING_MANAGE, False),
            # A developer authors deeply but governs nothing.
            (Role.DEVELOPER, Permission.MCP_INSTALL, True),
            (Role.DEVELOPER, Permission.API_KEY_CREATE, True),
            (Role.DEVELOPER, Permission.MEMBER_ASSIGN_ROLE, False),
            (Role.DEVELOPER, Permission.BILLING_MANAGE, False),
            # A manager governs people and settings but not money.
            (Role.MANAGER, Permission.MEMBER_ASSIGN_ROLE, True),
            (Role.MANAGER, Permission.SETTINGS_MANAGE, True),
            (Role.MANAGER, Permission.BILLING_MANAGE, False),
            # Admin adds billing on top of everything below it.
            (Role.ADMIN, Permission.BILLING_MANAGE, True),
            # A plain member runs agents but cannot delete them.
            (Role.MEMBER, Permission.AGENT_RUN, True),
            (Role.MEMBER, Permission.AGENT_DELETE, False),
            (Role.MEMBER, Permission.AUDIT_LOG_VIEW, False),
            # A viewer reads and nothing else.
            (Role.VIEWER, Permission.AGENT_VIEW, True),
            (Role.VIEWER, Permission.AGENT_RUN, False),
        ],
    )
    def test_matrix(self, role: Role, permission: Permission, expected: bool) -> None:
        assert has_permission(role, permission) is expected

    def test_developer_and_analyst_are_not_comparable_by_capability(self) -> None:
        """The point of the matrix existing alongside the linear rank.

        `developer` outranks `analyst`, so it inherits everything analyst
        has — but the reverse containment must not hold, or the two tiers
        would be redundant.
        """
        assert permissions_for(Role.ANALYST) < permissions_for(Role.DEVELOPER)
        assert not permissions_for(Role.DEVELOPER) <= permissions_for(Role.ANALYST)
