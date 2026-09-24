"""Unit and integration tests for the hashing module."""

import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.hashing import _get_stream_md5_cached, get_stream_md5
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


async def mock_ffmpeg_stream_success() -> AsyncGenerator[bytes, None]:
    """Mock of successful ffmpeg stream."""
    yield b"stream_data"


async def mock_ffmpeg_stream_failure() -> AsyncGenerator[bytes, None]:
    """Mock of failed ffmpeg stream."""
    raise FFmpegProcessError("ffmpeg failed")
    yield  # This line is unreachable, but makes the function a generator


@pytest.fixture(autouse=True)
def _clear_hashing_cache() -> None:
    """Clear the cache for get_stream_md5 before each test."""
    _get_stream_md5_cached.cache_clear()


@pytest.mark.unit
def test_get_stream_md5_caches_repeated_calls(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """get_stream_md5 calls ffmpeg only once for an unchanged file."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    stream = VideoStream(file=VideoFile(path=file_path), index=0)
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        return_value=mock_ffmpeg_stream_success(),
    )

    # Act
    get_stream_md5(stream)
    get_stream_md5(stream)

    # Assert
    mock_execute_ffmpeg.assert_called_once()


@pytest.mark.unit
def test_get_stream_md5_rehashes_when_file_stat_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """get_stream_md5 calls ffmpeg again when mtime or size changes."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    stream = VideoStream(file=VideoFile(path=file_path), index=0)
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        side_effect=[mock_ffmpeg_stream_success(), mock_ffmpeg_stream_success()],
    )

    # Act
    get_stream_md5(stream)
    # Prefer an explicit mtime over Path.touch(): on filesystems with 1s
    # mtime resolution, touch() in a fast test may leave mtime unchanged and
    # fail to bust the cache.
    os.utime(file_path, (1_700_000_000, 1_700_000_000))
    get_stream_md5(stream)

    # Assert
    assert mock_execute_ffmpeg.call_count == 2


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
    actual_md5 = get_stream_md5(stream)

    # Assert
    assert len(actual_md5) == 32
    assert all(c in "0123456789abcdef" for c in actual_md5)


@pytest.mark.unit
def test_get_stream_md5_raises_on_ffmpeg_failure(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """get_stream_md5 raises FFmpegProcessError when ffmpeg streaming fails."""
    # Arrange
    file_path = tmp_path / "test.ts"
    file_path.touch()
    mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        return_value=mock_ffmpeg_stream_failure(),
    )
    stream = VideoStream(file=VideoFile(path=file_path), index=0)

    # Act & Assert
    with pytest.raises(FFmpegProcessError, match="ffmpeg failed"):
        get_stream_md5(stream)
