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


def test_cli_options_recognized(mocker):
    """Test that the CLI recognizes the --crf and --preset options."""
    mock_ts2mp4 = mocker.patch("ts2mp4.ts2mp4.ts2mp4")

    # Simulate command-line arguments
    # Imports are placed inside the test function to ensure that the `app` object
    # is imported *after* `mock_ts2mp4` has been set up. This is crucial because
    # `typer.testing.CliRunner` directly imports and uses the `app` object,
    # and we need to ensure that when `app` is used, it sees the mocked version
    # of `ts2mp4.ts2mp4.ts2mp4`.
    from typer.testing import CliRunner

    from ts2mp4.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["dummy.ts", "--crf", "20", "--preset", "slow"])

    assert result.exit_code == 0
    mock_ts2mp4.assert_called_once_with(
        ts=mocker.ANY,
        crf=20,
        preset="slow",
    )


def test_cli_invalid_crf_value():
    """Test that the CLI handles invalid CRF values gracefully."""
    command = [
        "poetry",
        "run",
        "ts2mp4",
        "dummy.ts",
        "--crf",
        "invalid",
    ]
    # Create a dummy file
    with open("dummy.ts", "w") as f:
        f.write("dummy")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Invalid value for '--crf'" in result.stderr


def test_cli_invalid_preset_value(mocker):
    """Test that the CLI handles invalid preset values gracefully."""
    mock_ts2mp4 = mocker.patch("ts2mp4.ts2mp4.ts2mp4")

    # Simulate command-line arguments
    # Imports are placed inside the test function to ensure that the `app` object
    # is imported *after* `mock_ts2mp4` has been set up. This is crucial because
    # `typer.testing.CliRunner` directly imports and uses the `app` object,
    # and we need to ensure that when `app` is used, it sees the mocked version
    # of `ts2mp4.ts2mp4.ts2mp4`.
    from typer.testing import CliRunner

    from ts2mp4.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["dummy.ts", "--preset", "invalid_preset"])

    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 2  # Typer exits with code 2 for BadParameter
    assert "Invalid value for '--preset'" in result.output
    mock_ts2mp4.assert_not_called()
