import pytest

from agentverse_api.auth_service.domain.role import Role, satisfies


@pytest.mark.parametrize(
    ("actual", "minimum", "expected"),
    [
        (Role.OWNER, Role.OWNER, True),
        (Role.OWNER, Role.VIEWER, True),
        (Role.ADMIN, Role.OWNER, False),
        (Role.MEMBER, Role.ADMIN, False),
        (Role.VIEWER, Role.VIEWER, True),
        (Role.VIEWER, Role.MEMBER, False),
        (Role.ADMIN, Role.ADMIN, True),
    ],
)
def test_satisfies_respects_hierarchy(actual: Role, minimum: Role, expected: bool) -> None:
    assert satisfies(actual, minimum) is expected


def test_full_hierarchy_ordering() -> None:
    # owner > admin > member > viewer, exactly (CLAUDE.md §10).
    assert satisfies(Role.OWNER, Role.ADMIN)
    assert satisfies(Role.ADMIN, Role.MEMBER)
    assert satisfies(Role.MEMBER, Role.VIEWER)
    assert not satisfies(Role.VIEWER, Role.MEMBER)
    assert not satisfies(Role.MEMBER, Role.ADMIN)
    assert not satisfies(Role.ADMIN, Role.OWNER)
