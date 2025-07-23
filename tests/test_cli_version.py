"""Tests for the --version flag in the CLI."""

import pytest
from typer.testing import CliRunner

from ts2mp4 import _get_ts2mp4_version
from ts2mp4.cli import app

runner = CliRunner()


@pytest.mark.unit
def test_version_flag() -> None:
    """Test that the --version flag prints the version and exits."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"ts2mp4 version: {_get_ts2mp4_version()}" in result.stdout
