"""The continuous-control edge refuses managed serving with fixture-only evidence mapping."""

import pytest

from continuous_controls_monitoring.managed_readiness import (
    INCOMPLETE_MANAGED_OPERATIONS,
    assert_managed_profile_ready,
)


def test_offline_and_exit_profiles_remain_available() -> None:
    assert_managed_profile_ready("local")
    assert_managed_profile_ready("onprem")


def test_managed_profile_refuses_while_operations_are_placeholders() -> None:
    assert INCOMPLETE_MANAGED_OPERATIONS
    with pytest.raises(RuntimeError, match="not production ready"):
        assert_managed_profile_ready("gcp")
