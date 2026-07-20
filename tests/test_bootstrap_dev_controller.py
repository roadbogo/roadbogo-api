import pytest

from scripts.bootstrap_dev_controller import require_development_environment


@pytest.mark.parametrize("environment", ["local", "LOCAL", "test"])
def test_dev_controller_bootstrap_allows_only_development_environments(
    environment: str,
) -> None:
    require_development_environment(environment)


@pytest.mark.parametrize("environment", ["development", "staging", "production", "prod"])
def test_dev_controller_bootstrap_rejects_non_local_environments(
    environment: str,
) -> None:
    with pytest.raises(RuntimeError, match="local or test"):
        require_development_environment(environment)
