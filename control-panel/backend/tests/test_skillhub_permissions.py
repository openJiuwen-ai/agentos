"""权限矩阵 — Resource.SKILLS。"""

from app.iam.permissions import Action, PermissionService, Resource


def test_user_can_read_and_write_skills():
    assert PermissionService.check("user", Resource.SKILLS, Action.READ)
    assert PermissionService.check("user", Resource.SKILLS, Action.WRITE)


def test_admin_wildcard_grants_skills():
    assert PermissionService.check("admin", Resource.SKILLS, Action.WRITE)


def test_unknown_role_lacks_skills():
    assert not PermissionService.check("viewer", Resource.SKILLS, Action.WRITE)
