"""Unit and integration tests for the hashing module."""

from pathlib import Path
from typing import AsyncGenerator

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.hashing import _get_stream_md5_cached, get_stream_md5
from ts2mp4.media_info import AudioStream, Stream, VideoStream


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
def test_get_stream_md5_caching(mocker: MockerFixture) -> None:
    """Test that get_stream_md5 caches results."""
    file_path = Path("test.ts")
    stream = VideoStream(index=0, codec_type="video")

    mock_resolve = mocker.patch.object(Path, "resolve", return_value=file_path)
    mocker.patch.object(Path, "stat", return_value=mocker.Mock(st_mtime=1, st_size=1))

    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        return_value=mock_ffmpeg_stream_success(),
    )

    # Call twice
    get_stream_md5(file_path, stream)
    get_stream_md5(file_path, stream)

    # Assert that execute_ffmpeg was only called once
    mock_execute_ffmpeg.assert_called_once()
    mock_resolve.assert_called_with(strict=True)


@pytest.mark.unit
def test_get_stream_md5_cache_invalidation(mocker: MockerFixture) -> None:
    """Test that the cache is invalidated when the file is modified."""
    file_path = Path("test.ts")
    stream = VideoStream(index=0, codec_type="video")

    mock_resolve = mocker.patch.object(Path, "resolve", return_value=file_path)
    mock_stat = mocker.patch(
        "pathlib.Path.stat", return_value=mocker.Mock(st_mtime=1, st_size=1)
    )

    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        side_effect=[mock_ffmpeg_stream_success(), mock_ffmpeg_stream_success()],
    )

    # First call
    get_stream_md5(file_path, stream)

    # Simulate file modification
    mock_stat.return_value = mocker.Mock(st_mtime=2, st_size=2)

    # Second call
    get_stream_md5(file_path, stream)

    # Assert that execute_ffmpeg was called twice
    assert mock_execute_ffmpeg.call_count == 2
    mock_resolve.assert_called_with(strict=True)


@pytest.mark.integration
@pytest.mark.parametrize(
    "stream_index, codec_type",
    [
        (0, "video"),  # Video stream
        (1, "audio"),  # Audio stream
    ],
)
def test_get_stream_md5(ts_file: Path, stream_index: int, codec_type: str) -> None:
    """Test the get_stream_md5 function for different stream types."""
    stream: Stream
    if codec_type == "video":
        stream = VideoStream(index=stream_index, codec_type=codec_type)
    else:
        stream = AudioStream(index=stream_index, codec_type=codec_type)
    actual_md5 = get_stream_md5(ts_file, stream)
    # Check if the returned MD5 hash is a valid 32-character hexadecimal string
    assert len(actual_md5) == 32
    assert all(c in "0123456789abcdef" for c in actual_md5)


@pytest.mark.unit
@pytest.mark.parametrize(
    "stream_index, codec_type",
    [
        (0, "video"),  # Video stream
        (1, "audio"),  # Audio stream
    ],
)
def test_get_stream_md5_failure(
    mocker: MockerFixture, ts_file: Path, stream_index: int, codec_type: str
) -> None:
    """Test get_stream_md5 with a non-zero return code for different stream types."""
    mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg_streamed",
        return_value=mock_ffmpeg_stream_failure(),
    )
    stream: Stream
    if codec_type == "video":
        stream = VideoStream(index=stream_index, codec_type=codec_type)
    else:
        stream = AudioStream(index=stream_index, codec_type=codec_type)
    with pytest.raises(FFmpegProcessError, match="ffmpeg failed"):
        get_stream_md5(ts_file, stream)
