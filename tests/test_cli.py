import subprocess

import pytest


@pytest.mark.parametrize(
    "command",
    [
        ["poetry", "run", "ts2mp4", "--help"],
        ["poetry", "run", "python", "-m", "ts2mp4", "--help"],
    ],
)
def test_cli_entry_points_start_correctly(command):
    """Test that CLI entry points run without error and show help message."""
    result = subprocess.run(command, capture_output=True, text=True, check=True)

    # Check that the output contains the usage string to ensure the Typer CLI is running.
    assert "Usage:" in result.stdout
