from types import SimpleNamespace

import pytest

from app.core.exceptions import AppException
from app.dependencies.permissions import require_permissions


def current_user(*permissions: str):
    return SimpleNamespace(summary=SimpleNamespace(permissions=list(permissions)))


def test_permission_dependency_allows_every_required_permission() -> None:
    dependency = require_permissions("INCIDENT.READ_ALL", "CCTV.READ")

    result = dependency(current_user=current_user("CCTV.READ", "INCIDENT.READ_ALL"))

    assert result.summary.permissions == ["CCTV.READ", "INCIDENT.READ_ALL"]


def test_permission_dependency_rejects_a_missing_permission() -> None:
    dependency = require_permissions("INCIDENT.READ_ALL", "CCTV.READ")

    with pytest.raises(AppException) as error:
        dependency(current_user=current_user("INCIDENT.READ_ALL"))

    assert error.value.status_code == 403
    assert error.value.code == "AUTH_PERMISSION_DENIED"


def test_role_without_permission_is_rejected() -> None:
    dependency = require_permissions("CCTV.READ")
    user = SimpleNamespace(
        summary=SimpleNamespace(roles=["CONTROL_MANAGER"], permissions=[])
    )

    with pytest.raises(AppException) as error:
        dependency(current_user=user)

    assert error.value.code == "AUTH_PERMISSION_DENIED"


def test_all_permissions_are_required_not_just_one() -> None:
    dependency = require_permissions("INCIDENT.READ_ALL", "CCTV.READ")

    with pytest.raises(AppException) as error:
        dependency(current_user=current_user("CCTV.READ"))

    assert error.value.status_code == 403
