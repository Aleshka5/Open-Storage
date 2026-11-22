"""X-Auth-Roles projects onto the four storage roles. Nothing else computes a role."""

from __future__ import annotations

import pytest

from app.domain.value_objects.role import Role, role_from_auth_roles


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, Role.STRANGER),
        ("", Role.STRANGER),
        ("   ", Role.STRANGER),
        ("svc:storage:family", Role.FAMILY),
        ("svc:storage:admin", Role.ADMIN),
        ("svc:storage:family svc:storage:admin", Role.ADMIN),
        ("svc:storage:admin svc:storage:family", Role.ADMIN),
        ("svc:storage:blocked svc:storage:admin", Role.BLOCKED),
        ("svc:storage:admin svc:storage:blocked", Role.BLOCKED),
        ("svc:storage:blocked svc:storage:family", Role.BLOCKED),
        ("svc:storage:family svc:storage:blocked", Role.BLOCKED),
        ("svc:image:family", Role.STRANGER),
        ("svc:storage", Role.STRANGER),
        ("storage:family", Role.STRANGER),
        ("admin", Role.STRANGER),
        ("admin svc:storage:admin", Role.ADMIN),
        ("svc:storage:family svc:image:admin", Role.FAMILY),
    ],
)
def test_role_from_auth_roles(header: str | None, expected: Role) -> None:
    assert role_from_auth_roles(header) is expected


def test_role_gate_helpers_are_gone() -> None:
    assert not hasattr(Role, "can_access_shared")
    assert not hasattr(Role, "can_access_admin")
