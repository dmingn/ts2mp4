"""Unit tests for the ts2mp4 module."""

from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.media_info import Stream
from ts2mp4.ts2mp4 import (
    _build_ffmpeg_conversion_args,
    _perform_initial_conversion,
    ts2mp4,
)
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_build_ffmpeg_conversion_args(
    video_file_factory: Callable[..., VideoFile],
) -> None:
    """Test that _build_ffmpeg_conversion_args generates correct arguments."""
    output_path = Path("output.mp4")
    crf = 23
    preset = "medium"

    video_stream = Stream(codec_type="video", index=0)
    audio_stream1 = Stream(codec_type="audio", index=1, channels=2)
    audio_stream2 = Stream(codec_type="audio", index=3, channels=6)

    input_file = video_file_factory(
        streams=[video_stream, audio_stream1, audio_stream2]
    )

    stream_sources = {
        0: StreamSource(
            source_video_file=input_file,
            source_stream_index=video_stream.index,
            conversion_type=ConversionType.CONVERTED,
        ),
        1: StreamSource(
            source_video_file=input_file,
            source_stream_index=audio_stream1.index,
            conversion_type=ConversionType.CONVERTED,
        ),
        2: StreamSource(
            source_video_file=input_file,
            source_stream_index=audio_stream2.index,
            conversion_type=ConversionType.CONVERTED,
        ),
    }

    args = _build_ffmpeg_conversion_args(output_path, crf, preset, stream_sources)

    assert str(input_file.path) in args
    assert f"-map 0:{video_stream.index}" in " ".join(args)
    assert f"-map 0:{audio_stream1.index}" in " ".join(args)
    assert f"-map 0:{audio_stream2.index}" in " ".join(args)
    assert "libx265" in args


@pytest.mark.unit
def test_perform_initial_conversion(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that _perform_initial_conversion executes FFmpeg and returns a ConvertedVideoFile."""
    input_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, channels=2),
        ]
    )
    output_file = input_file.path.with_name("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg",
        return_value=FFmpegResult(returncode=0, stdout=b"", stderr=""),
    )
    mock_return = mocker.MagicMock(spec=ConvertedVideoFile)
    mock_return.stream_sources = {
        0: StreamSource(
            source_video_file=input_file,
            source_stream_index=0,
            conversion_type=ConversionType.CONVERTED,
        ),
        1: StreamSource(
            source_video_file=input_file,
            source_stream_index=1,
            conversion_type=ConversionType.CONVERTED,
        ),
    }
    mocker.patch(
        "ts2mp4.ts2mp4.ConvertedVideoFile",
        return_value=mock_return,
    )

    result = _perform_initial_conversion(input_file, output_file, crf, preset)

    assert isinstance(result, ConvertedVideoFile)
    assert len(result.stream_sources) == 2
    assert all(
        s.conversion_type == ConversionType.CONVERTED
        for s in result.stream_sources.values()
    )


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
