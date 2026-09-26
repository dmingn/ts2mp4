"""Unit tests for the conversion module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.conversion import execute_conversion
from ts2mp4.stream_source import StreamSources


@pytest.mark.unit
def test_execute_conversion_runs_ffmpeg_with_built_args(mocker: MockerFixture) -> None:
    """execute_conversion runs FFmpeg with the arguments built for the sources."""
    # Arrange
    stream_sources = StreamSources(root=())
    output_path = Path("output.mp4")

    mock_build_ffmpeg_args = mocker.patch(
        "ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"]
    )
    mock_execute_ffmpeg = mocker.patch("ts2mp4.conversion.execute_ffmpeg")
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    execute_conversion(stream_sources, output_path)

    # Assert
    mock_build_ffmpeg_args.assert_called_once_with(stream_sources, output_path)
    mock_execute_ffmpeg.assert_called_once_with(["mock_arg"])


@pytest.mark.unit
def test_execute_conversion_returns_converted_file_for_output(
    mocker: MockerFixture,
) -> None:
    """execute_conversion returns the output file paired with the sources."""
    # Arrange
    stream_sources = StreamSources(root=())
    output_path = Path("output.mp4")

    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.execute_ffmpeg")
    mock_converted_video_file = mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    converted_file = execute_conversion(stream_sources, output_path)

    # Assert
    mock_converted_video_file.assert_called_once_with(
        path=output_path, stream_sources=stream_sources
    )
    assert converted_file is mock_converted_video_file.return_value
