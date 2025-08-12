"""Unit tests for the ts2mp4 module."""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.media_info import Stream
from ts2mp4.stream_integrity import StreamIntegrityError
from ts2mp4.ts2mp4 import _perform_initial_conversion, ts2mp4
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    VideoFile,
)


@pytest.mark.unit
def test_perform_initial_conversion(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that _perform_initial_conversion executes FFmpeg and returns a ConvertedVideoFile."""
    mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg",
        return_value=FFmpegResult(returncode=0, stdout=b"", stderr=""),
    )
    input_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, channels=2),
        ]
    )
    output_path = input_file.path.with_name("output.mp4")
    output_path.touch()  # Create dummy file for Pydantic validation

    result = _perform_initial_conversion(input_file, output_path, 23, "medium")

    assert isinstance(result, ConvertedVideoFile)
    assert result.path == output_path
    assert len(result.stream_sources) == 2
    assert result.stream_sources[0].conversion_type == ConversionType.CONVERTED
    assert result.stream_sources[1].conversion_type == ConversionType.COPIED


@pytest.mark.unit
def test_perform_initial_conversion_ffmpeg_failure(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that _perform_initial_conversion raises RuntimeError on FFmpeg failure."""
    mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg",
        return_value=FFmpegResult(returncode=1, stdout=b"", stderr=""),
    )
    input_file = video_file_factory()
    output_path = input_file.path.with_name("output.mp4")

    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        _perform_initial_conversion(input_file, output_path, 23, "medium")


@pytest.mark.unit
def test_ts2mp4_success_flow(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test the successful conversion flow of the ts2mp4 function."""
    input_file = video_file_factory()
    output_path = input_file.path.with_name("output.mp4")

    mock_perform_initial_conversion = mocker.patch(
        "ts2mp4.ts2mp4._perform_initial_conversion",
        return_value=mocker.MagicMock(spec=ConvertedVideoFile),
    )
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_re_encode = mocker.patch("ts2mp4.ts2mp4.re_encode_mismatched_audio_streams")

    ts2mp4(input_file, output_path, 23, "medium")

    mock_perform_initial_conversion.assert_called_once_with(
        input_file, output_path, 23, "medium"
    )
    mock_verify_streams.assert_called_once_with(
        mock_perform_initial_conversion.return_value
    )
    mock_re_encode.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_re_encodes_on_failure(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that audio re-encoding is triggered on stream integrity failure."""
    input_file = video_file_factory()
    output_path = input_file.path.with_name("output.mp4")
    temp_output_path = output_path.with_suffix(".mp4.temp")

    # The file returned by the initial conversion
    encoded_file = converted_video_file_factory(source_video_file=input_file)

    mocker.patch("ts2mp4.ts2mp4._perform_initial_conversion", return_value=encoded_file)
    mocker.patch(
        "ts2mp4.ts2mp4.verify_streams",
        side_effect=StreamIntegrityError("mismatch"),
    )
    mock_re_encode = mocker.patch("ts2mp4.ts2mp4.re_encode_mismatched_audio_streams")
    mocker.patch("pathlib.Path.replace")

    ts2mp4(input_file, output_path, 23, "medium")

    mock_re_encode.assert_called_once_with(
        original_file=input_file,
        encoded_file=encoded_file,
        output_file=temp_output_path,
    )
