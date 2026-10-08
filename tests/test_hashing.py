"""Unit and integration tests for the hashing module."""

import os
from pathlib import Path

import pytest

from tests.helpers import FakeFFmpegRunner, StubVideoFile
from ts2mp4.ffmpeg import FFmpegProcessError, SubprocessFFmpegRunner
from ts2mp4.ffmpeg_input_args import build_zero_based_input_args
from ts2mp4.ffprobe_schema import FFprobeFormat, FFprobeOutput
from ts2mp4.hashing import (
    FrameHash,
    _get_frame_hashes_cached,
    get_frame_hashes,
    parse_framemd5,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream

_FRAMEMD5_OUTPUT = b"""#format: frame checksums
#version: 2
#hash: MD5
#tb 0: 1/48000
#media_type 0: audio
#codec_id 0: pcm_s16le
#sample_rate 0: 48000
#channel_layout_name 0: stereo
#stream#, dts,        pts, duration,     size, hash
0,          0,          0,     1024,     4096, 57b8b5c4305040bdc2935aaaa2802898
0,       1024,       1024,     1024,     4096, ded585697000a346360d74709bb89fa7
"""


@pytest.fixture(autouse=True)
def _clear_hashing_cache() -> None:
    """Clear the cache for get_frame_hashes before each test."""
    _get_frame_hashes_cached.cache_clear()


@pytest.fixture
def stub_stream(tmp_path: Path) -> VideoStream:
    """Return a video stream of an empty file starting at 100 seconds."""
    file_path = tmp_path / "test.ts"
    file_path.touch()
    return VideoStream(
        file=StubVideoFile(
            path=file_path,
            stub_probe=FFprobeOutput(format=FFprobeFormat(start_time=100.0)),
        ),
        index=0,
    )


@pytest.mark.unit
def test_parse_framemd5_reads_timestamps_in_seconds_and_hashes() -> None:
    """parse_framemd5 converts each pts from the time base into seconds."""
    # Act
    frames = parse_framemd5(_FRAMEMD5_OUTPUT.decode().splitlines())

    # Assert
    assert frames == (
        FrameHash(pts=0.0, md5="57b8b5c4305040bdc2935aaaa2802898"),
        FrameHash(pts=1024 / 48000, md5="ded585697000a346360d74709bb89fa7"),
    )


@pytest.mark.unit
def test_get_frame_hashes_reads_timestamps_from_the_file_start(
    stub_stream: VideoStream,
) -> None:
    """get_frame_hashes opens the file shifted so that it starts at zero."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stdout=_FRAMEMD5_OUTPUT)

    # Act
    get_frame_hashes(stub_stream, ffmpeg_runner)

    # Assert
    (args,) = ffmpeg_runner.calls
    input_args = build_zero_based_input_args(
        stub_stream.file.path, stub_stream.file.start_time
    )
    assert "-copyts" in args
    assert any(args[i : i + len(input_args)] == input_args for i in range(len(args)))


@pytest.mark.unit
def test_get_frame_hashes_caches_repeated_calls(stub_stream: VideoStream) -> None:
    """get_frame_hashes calls ffmpeg only once for an unchanged file."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stdout=_FRAMEMD5_OUTPUT)

    # Act
    get_frame_hashes(stub_stream, ffmpeg_runner)
    get_frame_hashes(stub_stream, ffmpeg_runner)

    # Assert
    assert len(ffmpeg_runner.calls) == 1


@pytest.mark.unit
def test_get_frame_hashes_rehashes_when_file_stat_changes(
    stub_stream: VideoStream,
) -> None:
    """get_frame_hashes calls ffmpeg again when mtime or size changes."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stdout=_FRAMEMD5_OUTPUT)

    # Act
    get_frame_hashes(stub_stream, ffmpeg_runner)
    # Prefer an explicit mtime over Path.touch(): on filesystems with 1s
    # mtime resolution, touch() in a fast test may leave mtime unchanged and
    # fail to bust the cache.
    os.utime(stub_stream.file.path, (1_700_000_000, 1_700_000_000))
    get_frame_hashes(stub_stream, ffmpeg_runner)

    # Assert
    assert len(ffmpeg_runner.calls) == 2


@pytest.mark.unit
def test_get_frame_hashes_raises_on_ffmpeg_failure(stub_stream: VideoStream) -> None:
    """get_frame_hashes raises FFmpegProcessError when ffmpeg streaming fails."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(error=FFmpegProcessError("ffmpeg failed"))

    # Act & Assert
    with pytest.raises(FFmpegProcessError, match="ffmpeg failed"):
        get_frame_hashes(stub_stream, ffmpeg_runner)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("stream_index", "stream_factory"),
    [
        pytest.param(0, VideoStream, id="video"),
        pytest.param(1, AudioStream, id="audio"),
    ],
)
def test_get_frame_hashes_starts_at_the_stream_start_offset(
    ts_file: Path,
    stream_index: int,
    stream_factory: type[VideoStream | AudioStream],
) -> None:
    """get_frame_hashes returns frames that start at the stream start offset."""
    # Arrange
    stream = stream_factory(file=VideoFile(path=ts_file), index=stream_index)

    # Act
    frames = get_frame_hashes(stream, SubprocessFFmpegRunner())

    # Assert
    assert frames[0].pts == pytest.approx(stream.start_offset, abs=0.001)
