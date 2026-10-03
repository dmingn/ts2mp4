"""Unit tests for the conversion module."""

import io
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.conversion import execute_conversion
from ts2mp4.conversion_plan import FileConversionPlan


class _TTYStringIO(io.StringIO):
    """A StringIO that reports itself as a TTY."""

    def isatty(self) -> bool:
        return True


@pytest.mark.unit
def test_execute_conversion_runs_ffmpeg_with_built_args(mocker: MockerFixture) -> None:
    """execute_conversion runs FFmpeg with the arguments built for the plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=())
    output_path = Path("output.mp4")
    ffmpeg_runner = FakeFFmpegRunner()

    mock_build_ffmpeg_args = mocker.patch(
        "ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"]
    )
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    execute_conversion(file_conversion_plan, output_path, ffmpeg_runner)

    # Assert
    mock_build_ffmpeg_args.assert_called_once_with(file_conversion_plan, output_path)
    assert ffmpeg_runner.calls == [["mock_arg"]]


@pytest.mark.unit
def test_execute_conversion_returns_converted_file_for_output(
    mocker: MockerFixture,
) -> None:
    """execute_conversion returns the output file paired with the plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=())
    output_path = Path("output.mp4")

    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mock_converted_video_file = mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    converted_file = execute_conversion(
        file_conversion_plan, output_path, FakeFFmpegRunner()
    )

    # Assert
    mock_converted_video_file.assert_called_once_with(
        path=output_path, file_conversion_plan=file_conversion_plan
    )
    assert converted_file is mock_converted_video_file.return_value


@pytest.mark.unit
def test_execute_conversion_shows_progress_on_tty(mocker: MockerFixture) -> None:
    """execute_conversion shows the reported position on a TTY stderr."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [2.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mp4"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "Encoding: 2s" in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_caps_progress_at_source_duration(
    mocker: MockerFixture,
) -> None:
    """execute_conversion does not show progress beyond the source duration."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")
    mocker.patch.object(
        FileConversionPlan,
        "max_source_duration",
        new_callable=mocker.PropertyMock,
        return_value=3.0,
    )

    out_seconds = [3.6]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mp4"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "3/3" in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_does_not_show_negative_progress(
    mocker: MockerFixture,
) -> None:
    """execute_conversion does not move the progress below zero."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [-5.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mp4"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "-5s" not in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_shows_nothing_on_non_tty(mocker: MockerFixture) -> None:
    """execute_conversion does not show progress when stderr is not a TTY."""
    # Arrange
    stderr = io.StringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [2.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mp4"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert stderr.getvalue() == ""
