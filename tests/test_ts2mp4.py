"""Unit tests for the ts2mp4 module."""

from types import MappingProxyType
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.ts2mp4 import (
    ConversionPlan,
    _perform_initial_conversion,
    _prepare_initial_conversion_plan,
    ts2mp4,
)
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    VideoFile,
)


@pytest.mark.unit
def test_prepare_initial_conversion_plan(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that _prepare_initial_conversion_plan returns correct results."""
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(
            streams=(
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1, channels=2),
                Stream(codec_type="audio", index=2, channels=0),
                Stream(codec_type="audio", index=3, channels=6),
            )
        ),
    )
    input_file = video_file_factory()
    output_path = input_file.path.with_name("output.mp4")

    result = _prepare_initial_conversion_plan(input_file, output_path, 23, "medium")

    assert isinstance(result, ConversionPlan)
    assert isinstance(result.stream_sources, MappingProxyType)
    assert len(result.stream_sources) == 3
    assert result.stream_sources[0].conversion_type == ConversionType.CONVERTED
    assert result.stream_sources[1].conversion_type == ConversionType.COPIED
    assert result.stream_sources[2].conversion_type == ConversionType.COPIED

    assert isinstance(result.ffmpeg_args, list)
    assert str(input_file.path) in result.ffmpeg_args
    assert "-map 0:0" in " ".join(result.ffmpeg_args)
    assert "-map 0:1" in " ".join(result.ffmpeg_args)
    assert "-map 0:3" in " ".join(result.ffmpeg_args)


@pytest.mark.unit
def test_perform_initial_conversion(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that _perform_initial_conversion executes FFmpeg and returns a ConvertedVideoFile."""
    input_file = video_file_factory()
    output_file = input_file.path.with_name("output.mp4")
    output_file.touch()

    mock_ffmpeg_result = FFmpegResult(returncode=0, stdout=b"", stderr="")
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg", return_value=mock_ffmpeg_result
    )
    mock_plan = ConversionPlan(
        stream_sources=MappingProxyType({}), ffmpeg_args=["ffmpeg"]
    )
    mock_prepare = mocker.patch(
        "ts2mp4.ts2mp4._prepare_initial_conversion_plan", return_value=mock_plan
    )

    result = _perform_initial_conversion(input_file, output_file, 23, "medium")

    mock_prepare.assert_called_once_with(input_file, output_file, 23, "medium")
    mock_execute_ffmpeg.assert_called_once_with(["ffmpeg"])
    assert isinstance(result, ConvertedVideoFile)
    assert result.path == output_file


@pytest.mark.unit
def test_ts2mp4_success_flow(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test the successful conversion flow of the ts2mp4 function."""
    input_file = video_file_factory()
    output_file = input_file.path.with_name("output.mp4")

    mock_perform_initial_conversion = mocker.patch(
        "ts2mp4.ts2mp4._perform_initial_conversion",
        return_value=mocker.MagicMock(spec=ConvertedVideoFile),
    )
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_re_encode = mocker.patch("ts2mp4.ts2mp4.re_encode_mismatched_audio_streams")

    ts2mp4(input_file, output_file, 23, "medium")

    mock_perform_initial_conversion.assert_called_once_with(
        input_file, output_file, 23, "medium"
    )
    mock_verify_streams.assert_called_once()
    mock_re_encode.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_re_encodes_on_failure(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that audio re-encoding is triggered on stream integrity failure."""
    input_file = video_file_factory()
    output_file = input_file.path.with_name("output.mp4")
    temp_output_file = output_file.with_suffix(".mp4.temp")

    converted_file = converted_video_file_factory(
        source_video_file=input_file, filename=output_file.name
    )

    mocker.patch(
        "ts2mp4.ts2mp4._perform_initial_conversion", return_value=converted_file
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_streams", side_effect=RuntimeError("integrity error")
    )
    mock_re_encode = mocker.patch(
        "ts2mp4.ts2mp4.re_encode_mismatched_audio_streams",
        return_value=mocker.MagicMock(spec=ConvertedVideoFile),
    )
    mocker.patch("pathlib.Path.replace")

    ts2mp4(input_file, output_file, 23, "medium")

    mock_re_encode.assert_called_once_with(
        original_file=input_file,
        encoded_file=converted_file,
        output_file=temp_output_file,
    )
