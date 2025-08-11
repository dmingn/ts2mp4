"""Unit and integration tests for the CLI."""

import subprocess
from pathlib import Path

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture


@pytest.mark.integration
@pytest.mark.parametrize(
    "command",
    [
        ["poetry", "run", "ts2mp4", "--help"],
        ["poetry", "run", "python", "-m", "ts2mp4", "--help"],
    ],
)
def test_cli_entry_points_start_correctly(command: list[str]) -> None:
    """Test that CLI entry points run without error and show help message."""
    result = subprocess.run(command, capture_output=True, text=True, check=True)

    # Check that the output contains the usage string to ensure the Typer CLI is
    # running.
    assert "Usage:" in result.stdout


@pytest.mark.integration
def test_cli_options_recognized(mocker: MockerFixture, tmp_path: Path) -> None:
    """Test that the CLI recognizes the --crf and --preset options."""
    mock_ts2mp4 = mocker.patch("ts2mp4.cli.ts2mp4")
    mocker.patch("pathlib.Path.replace")
    mock_stat_result = mocker.MagicMock()
    mock_stat_result.st_size = 100
    mock_stat_result.st_mode = 0o100644
    mocker.patch("pathlib.Path.stat", return_value=mock_stat_result)
    mocker.patch("pathlib.Path.exists", return_value=False)

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
        input_file=mocker.ANY,
        output_path=mocker.ANY,
        crf=20,
        preset="slow",
    )


@pytest.mark.integration
def test_cli_invalid_crf_value(tmp_path: Path) -> None:
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
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0


@pytest.mark.integration
def test_cli_invalid_preset_value(mocker: MockerFixture, tmp_path: Path) -> None:
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
    result = runner.invoke(app, [str(dummy_ts_path), "--preset", "invalid_preset"])

    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 2  # Typer exits with code 2 for BadParameter
    mock_ts2mp4.assert_not_called()


@pytest.mark.integration
@freeze_time("2023-01-01 12:00:00")
def test_log_file_creation(mocker: MockerFixture, tmp_path: Path) -> None:
    """Test that a log file is created with the correct naming convention."""
    mock_ts2mp4 = mocker.patch("ts2mp4.cli.ts2mp4")
    mocker.patch("pathlib.Path.replace")
    mock_stat_result = mocker.MagicMock()
    mock_stat_result.st_size = 100
    mock_stat_result.st_mode = 0o100644
    mocker.patch("pathlib.Path.stat", return_value=mock_stat_result)
    mocker.patch("pathlib.Path.exists", return_value=False)
    mock_logfile = mocker.patch("logzero.logfile")

    from typer.testing import CliRunner

    from ts2mp4.cli import app

    dummy_ts_path = tmp_path / "dummy.ts"
    dummy_ts_path.write_text("dummy")
    runner = CliRunner()
    result = runner.invoke(app, [str(dummy_ts_path)])

    assert result.exit_code == 0
    mock_ts2mp4.assert_called_once()
    mock_logfile.assert_called_once()

    expected_log_file = tmp_path / "dummy-20230101120000.log"
    mock_logfile.assert_called_with(str(expected_log_file))
