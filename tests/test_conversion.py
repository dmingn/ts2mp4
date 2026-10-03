"""Unit tests for the conversion module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.conversion import execute_conversion
from ts2mp4.conversion_plan import FileConversionPlan


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
