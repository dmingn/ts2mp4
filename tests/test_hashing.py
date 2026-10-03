"""Unit and integration tests for the hashing module."""

import os
from pathlib import Path

import pytest

from tests.helpers import FakeFFmpegRunner
from ts2mp4.ffmpeg import FFmpegProcessError, SubprocessFFmpegRunner
from ts2mp4.hashing import _get_stream_md5_cached, get_stream_md5
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


@pytest.fixture(autouse=True)
def _clear_hashing_cache() -> None:
    """Clear the cache for get_stream_md5 before each test."""
    _get_stream_md5_cached.cache_clear()


@pytest.mark.unit
def test_get_stream_md5_caches_repeated_calls(tmp_path: Path) -> None:
    """get_stream_md5 calls ffmpeg only once for an unchanged file."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    stream = VideoStream(file=VideoFile(path=file_path), index=0)
    ffmpeg_runner = FakeFFmpegRunner(stdout=b"stream_data")

    # Act
    get_stream_md5(stream, ffmpeg_runner)
    get_stream_md5(stream, ffmpeg_runner)

    # Assert
    assert len(ffmpeg_runner.calls) == 1


@pytest.mark.unit
def test_get_stream_md5_rehashes_when_file_stat_changes(tmp_path: Path) -> None:
    """get_stream_md5 calls ffmpeg again when mtime or size changes."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    stream = VideoStream(file=VideoFile(path=file_path), index=0)
    ffmpeg_runner = FakeFFmpegRunner(stdout=b"stream_data")

    # Act
    get_stream_md5(stream, ffmpeg_runner)
    # Prefer an explicit mtime over Path.touch(): on filesystems with 1s
    # mtime resolution, touch() in a fast test may leave mtime unchanged and
    # fail to bust the cache.
    os.utime(file_path, (1_700_000_000, 1_700_000_000))
    get_stream_md5(stream, ffmpeg_runner)

    # Assert
    assert len(ffmpeg_runner.calls) == 2


@pytest.mark.integration
@pytest.mark.parametrize(
    ("stream_index", "stream_factory"),
    [
        pytest.param(0, VideoStream, id="video"),
        pytest.param(1, AudioStream, id="audio"),
    ],
)
def test_get_stream_md5_returns_hex_digest(
    ts_file: Path,
    stream_index: int,
    stream_factory: type[VideoStream | AudioStream],
) -> None:
    """get_stream_md5 returns a 32-character hex digest for a real stream."""
    # Arrange
    stream = stream_factory(file=VideoFile(path=ts_file), index=stream_index)

    # Act
    actual_md5 = get_stream_md5(stream, SubprocessFFmpegRunner())

    # Assert
    assert len(actual_md5) == 32
    assert all(c in "0123456789abcdef" for c in actual_md5)


@pytest.mark.unit
def test_get_stream_md5_raises_on_ffmpeg_failure(tmp_path: Path) -> None:
    """get_stream_md5 raises FFmpegProcessError when ffmpeg streaming fails."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    stream = VideoStream(file=VideoFile(path=file_path), index=0)
    ffmpeg_runner = FakeFFmpegRunner(error=FFmpegProcessError("ffmpeg failed"))

    # Act & Assert
    with pytest.raises(FFmpegProcessError, match="ffmpeg failed"):
        get_stream_md5(stream, ffmpeg_runner)
