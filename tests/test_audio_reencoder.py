"""Unit and integration tests for the audio_reencoder module."""

from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import re_encode_mismatched_audio_streams
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.media_info import Stream, get_media_info
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_re_encode_on_hash_mismatch(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that a stream is re-encoded if its hash mismatches."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.audio_reencoder.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = MagicMock(returncode=0)
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=True)
    mocker.patch(
        "ts2mp4.audio_reencoder.get_stream_md5", side_effect=["hash1", "hash2"]
    )

    original_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, codec_name="aac"),
        ]
    )
    encoded_file = converted_video_file_factory(source_video_file=original_file)
    output_file = original_file.path.with_name("output.mp4")
    output_file.touch()

    re_encode_mismatched_audio_streams(original_file, encoded_file, output_file)

    call_args = mock_execute_ffmpeg.call_args.args[0]
    assert "libfdk_aac" in " ".join(call_args)


@pytest.mark.unit
def test_re_encode_on_missing_stream(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that a stream is re-encoded if it is missing from the encoded file."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.audio_reencoder.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = MagicMock(returncode=0)
    mocker.patch("ts2mp4.audio_reencoder.get_stream_md5", return_value="some_hash")

    # Original has 2 audio streams
    original_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, codec_name="aac"),
            Stream(codec_type="audio", index=2, codec_name="aac"),
        ]
    )
    # Encoded only has 1 audio stream
    encoded_file = converted_video_file_factory(
        source_video_file=original_file,
        stream_sources={
            0: StreamSource(
                source_video_file=original_file,
                source_stream_index=0,
                conversion_type=ConversionType.CONVERTED,
            ),
            1: StreamSource(
                source_video_file=original_file,
                source_stream_index=1,
                conversion_type=ConversionType.COPIED,
            ),
        },
    )
    output_file = original_file.path.with_name("output.mp4")
    output_file.touch()

    re_encode_mismatched_audio_streams(original_file, encoded_file, output_file)

    # Expect 3 map arguments: 1 for video, 1 for copied audio, 1 for re-encoded audio
    call_args = mock_execute_ffmpeg.call_args.args[0]
    assert call_args.count("-map") == 3


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams_integration(
    tmp_path: Path, ts_file: Path
) -> None:
    """Tests the re-encoding function with a real video file."""
    encoded_file_path = tmp_path / "encoded_missing_stream.mp4"
    execute_ffmpeg(
        [
            "-i",
            str(ts_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-codec",
            "copy",
            str(encoded_file_path),
        ]
    )

    original_video_file = VideoFile(path=ts_file)
    encoded_video_file = ConvertedVideoFile(
        path=encoded_file_path,
        stream_sources={
            0: StreamSource(
                source_video_file=original_video_file,
                source_stream_index=0,
                conversion_type=ConversionType.CONVERTED,
            ),
            1: StreamSource(
                source_video_file=original_video_file,
                source_stream_index=1,
                conversion_type=ConversionType.COPIED,
            ),
        },
    )

    output_file = tmp_path / "output.mp4"
    result = re_encode_mismatched_audio_streams(
        original_file=original_video_file,
        encoded_file=encoded_video_file,
        output_file=output_file,
    )

    original_media_info = get_media_info(ts_file)
    output_media_info = get_media_info(output_file)

    assert len(output_media_info.streams) == len(original_media_info.streams)
    assert result.stream_sources[0].conversion_type == ConversionType.COPIED
    assert result.stream_sources[1].conversion_type == ConversionType.COPIED
    assert result.stream_sources[2].conversion_type == ConversionType.RE_ENCODED
