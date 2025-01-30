"""Fixtures for testing."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: bool) -> None:  # noqa: ARG001, FBT001
    """Auto enable custom integration."""
    return
