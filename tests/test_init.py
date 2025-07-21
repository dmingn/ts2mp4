"""Unit tests for the __init__ module."""

import importlib.metadata

import pytest
from pytest_mock import MockerFixture

from ts2mp4 import _get_ts2mp4_version


@pytest.mark.unit
def test_get_ts2mp4_version_success(mocker: MockerFixture) -> None:
    """Test that _get_ts2mp4_version returns the version on success."""
    mocker.patch("importlib.metadata.version", return_value="1.2.3")
    assert _get_ts2mp4_version() == "1.2.3"


@pytest.mark.unit
def test_get_ts2mp4_version_package_not_found(mocker: MockerFixture) -> None:
    """Test that _get_ts2mp4_version returns 'unknown' on PackageNotFoundError."""
    mocker.patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    )
    assert _get_ts2mp4_version() == "Unknown"
