"""Unit and integration tests for the audio_reencoder module."""

from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import (
    ReEncodeResult,
    _prepare_audio_re_encode,
    re_encode_mismatched_audio_streams,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.media_info import Stream, get_media_info
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_prepare_audio_re_encode_no_mismatch(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that _prepare_audio_re_encode returns None when streams match."""
    original_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        ]
    )
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
    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=True)

    result = _prepare_audio_re_encode(original_file, encoded_file, Path("output.mp4"))
    assert result is None


@pytest.mark.unit
def test_prepare_audio_re_encode_with_mismatch(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that _prepare_audio_re_encode returns correct results for mismatched streams."""
    original_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, codec_name="aac"),
        ]
    )
    encoded_file = converted_video_file_factory(source_video_file=original_file)
    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=False)
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=True)

    result = _prepare_audio_re_encode(original_file, encoded_file, Path("output.mp4"))

    assert isinstance(result, ReEncodeResult)
    assert len(result.stream_sources) > 0
    assert any(
        s.conversion_type == ConversionType.RE_ENCODED
        for s in result.stream_sources.values()
    )
    assert "libfdk_aac" in " ".join(result.ffmpeg_args)


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams(tmp_path: Path, ts_file: Path) -> None:
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
    original_media_info = get_media_info(ts_file)
    video_stream = next(
        s for s in original_media_info.streams if s.codec_type == "video"
    )
    audio_stream = next(
        s for s in original_media_info.streams if s.codec_type == "audio"
    )

    encoded_video_file = ConvertedVideoFile(
        path=encoded_file_path,
        stream_sources={
            0: StreamSource(
                source_video_file=original_video_file,
                source_stream_index=video_stream.index,
                conversion_type=ConversionType.CONVERTED,
            ),
            1: StreamSource(
                source_video_file=original_video_file,
                source_stream_index=audio_stream.index,
                conversion_type=ConversionType.CONVERTED,
            ),
        },
    )

    output_file = tmp_path / "output.mp4"
    result = re_encode_mismatched_audio_streams(
        original_file=original_video_file,
        encoded_file=encoded_video_file,
        output_file=output_file,
    )

    assert result is not None
    output_media_info = get_media_info(output_file)

    assert len(output_media_info.streams) == len(original_media_info.streams)
    assert result.stream_sources[0].conversion_type == ConversionType.COPIED
    assert result.stream_sources[1].conversion_type == ConversionType.COPIED
    assert result.stream_sources[2].conversion_type == ConversionType.RE_ENCODED
