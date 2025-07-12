import os
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


def test_cli_options_recognized(mocker, tmp_path):
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

    dummy_ts_path = tmp_path / "dummy.ts"
    dummy_ts_path.write_text("dummy")
    runner = CliRunner()
    result = runner.invoke(app, [str(dummy_ts_path), "--crf", "20", "--preset", "slow"])

    assert result.exit_code == 0
    mock_ts2mp4.assert_called_once_with(
        ts=mocker.ANY,
        crf=20,
        preset="slow",
    )


def test_cli_invalid_crf_value(tmp_path):
    """Test that the CLI handles invalid CRF values gracefully."""
    dummy_ts_path = tmp_path / "dummy.ts"
    dummy_ts_path.write_text("dummy")
    command = [
        "poetry",
        "run",
        "ts2mp4",
        str(dummy_ts_path),
        "--crf",
        "invalid",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, env={"NO_COLOR": "1", **os.environ}
    )
    assert result.returncode != 0
    assert "Invalid value" in result.stderr and "--crf" in result.stderr


def test_cli_invalid_preset_value(mocker, tmp_path):
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

    dummy_ts_path = tmp_path / "dummy.ts"
    dummy_ts_path.write_text("dummy")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [str(dummy_ts_path), "--preset", "invalid_preset"],
        env={"NO_COLOR": "1", **os.environ},
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 2  # Typer exits with code 2 for BadParameter
    assert "Invalid value" in result.output and "--preset" in result.output
    mock_ts2mp4.assert_not_called()
