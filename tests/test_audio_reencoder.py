"""Unit and integration tests for the audio_reencoder module."""

from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import (
    _build_re_encode_ffmpeg_args,
    re_encode_mismatched_audio_streams,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.media_info import MediaInfo, Stream, get_media_info
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_build_re_encode_ffmpeg_args(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that FFmpeg arguments for re-encoding are built correctly."""
    original_file = video_file_factory(
        "original.ts", streams=[Stream(codec_type="audio", index=1, codec_name="aac")]
    )
    encoded_file = converted_video_file_factory(
        "encoded.mp4", source_video_file=original_file
    )
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(streams=[Stream(codec_type="video", index=0)]),
    )
    mocker.patch(
        "ts2mp4.video_file.VideoFile.get_stream_by_index",
        side_effect=lambda index: {1: original_file.media_info.streams[0]}.get(index),
    )
    mocker.patch(
        "ts2mp4.video_file.ConvertedVideoFile.get_stream_by_index",
        side_effect=lambda index: {0: encoded_file.media_info.streams[0]}.get(index),
    )

    stream_sources = {
        0: StreamSource(
            source_video_file=encoded_file,
            source_stream_index=0,
            conversion_type=ConversionType.COPIED,
        ),
        1: StreamSource(
            source_video_file=original_file,
            source_stream_index=1,
            conversion_type=ConversionType.RE_ENCODED,
        ),
    }

    args = _build_re_encode_ffmpeg_args(Path("output.mp4"), stream_sources)

    assert str(original_file.path) in " ".join(args)
    assert str(encoded_file.path) in " ".join(args)

    source_files = {original_file.path, encoded_file.path}
    input_files = sorted(list(source_files))
    input_map = {path: i for i, path in enumerate(input_files)}

    video_map = (
        f"-map {input_map[encoded_file.path]}:{stream_sources[0].source_stream_index}"
    )
    audio_map = (
        f"-map {input_map[original_file.path]}:{stream_sources[1].source_stream_index}"
    )

    assert video_map in " ".join(args)
    assert audio_map in " ".join(args)


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams(
    tmp_path: Path, ts_file: Path, video_file_factory: Callable[..., VideoFile]
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
