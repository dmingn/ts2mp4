"""Unit and integration tests for the media_info module."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import (
    Format,
    MediaInfo,
    Stream,
    _get_media_info_cached,
    get_media_info,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _get_media_info_cached.cache_clear()


@pytest.fixture()
def mock_path() -> MagicMock:
    """Return a mock Path object."""
    mock = MagicMock(spec=Path)
    mock.resolve.return_value = mock
    mock.stat.return_value = MagicMock(st_mtime=123.45, st_size=67890)
    return mock


@pytest.mark.unit
def test_get_media_info_success(mocker: MockerFixture, mock_path: MagicMock) -> None:
    """Test that get_media_info returns a MediaInfo object on success."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    ffprobe_output = {
        "streams": [
            {
                "codec_type": "video",
                "index": 0,
                "codec_name": "h264",
            },
            {
                "codec_type": "audio",
                "index": 1,
                "codec_name": "aac",
                "profile": "LC",
                "channels": 2,
                "sample_rate": 48000,
                "bit_rate": 192000,
            },
            {
                "codec_type": "audio",
                "index": 2,
                "codec_name": "mp3",
                "profile": "unknown",
                "channels": 1,
                "sample_rate": 44100,
                "bit_rate": 128000,
            },
        ],
        "format": {"format_name": "mpegts"},
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result = get_media_info(mock_path)

    # Assert
    expected = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0, codec_name="h264"),
            Stream(
                codec_type="audio",
                index=1,
                codec_name="aac",
                profile="LC",
                channels=2,
                sample_rate=48000,
                bit_rate=192000,
            ),
            Stream(
                codec_type="audio",
                index=2,
                codec_name="mp3",
                profile="unknown",
                channels=1,
                sample_rate=44100,
                bit_rate=128000,
            ),
        ),
        format=Format(format_name="mpegts"),
    )
    assert result == expected
    mock_execute_ffprobe.assert_called_once()
    mock_path.resolve.assert_called_once_with(strict=True)
    mock_path.stat.assert_called_once()


@pytest.mark.unit
def test_get_media_info_failure(mocker: MockerFixture, mock_path: MagicMock) -> None:
    """Test that get_media_info raises a RuntimeError on ffprobe failure."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_execute_ffprobe.return_value = mock_result

    # Act & Assert
    with pytest.raises(RuntimeError):
        get_media_info(mock_path)


@pytest.mark.unit
def test_get_media_info_invalid_json(
    mocker: MockerFixture, mock_path: MagicMock
) -> None:
    """Test that get_media_info raises a RuntimeError on invalid JSON."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = b"invalid json"
    mock_execute_ffprobe.return_value = mock_result

    # Act & Assert
    with pytest.raises(json.JSONDecodeError):
        get_media_info(mock_path)


@pytest.mark.unit
def test_get_media_info_ignores_unknown_fields(
    mocker: MockerFixture, mock_path: MagicMock
) -> None:
    """Test that get_media_info ignores unknown fields in the JSON output."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    ffprobe_output = {
        "streams": [],
        "format": {"format_name": "test_format"},
        "unknown_top_level_field": "this should be ignored",
        "another_extra_field": 123,
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result = get_media_info(mock_path)

    # Assert
    expected = MediaInfo(
        streams=(),
        format=Format(format_name="test_format"),
    )
    assert result == expected
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.unit
def test_get_media_info_cached(mocker: MockerFixture, mock_path: MagicMock) -> None:
    """Test that get_media_info caches the result."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    ffprobe_output = {
        "streams": [
            {"codec_type": "video", "index": 0, "codec_name": "h264"},
            {"codec_type": "audio", "index": 1, "codec_name": "aac"},
        ],
        "format": {"format_name": "mpegts"},
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result1 = get_media_info(mock_path)
    result2 = get_media_info(mock_path)

    # Assert
    assert result1 is result2
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.unit
def test_get_media_info_cache_miss(mocker: MockerFixture, mock_path: MagicMock) -> None:
    """Test that get_media_info misses the cache if the file is modified."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    ffprobe_output = {
        "streams": [
            {"codec_type": "video", "index": 0, "codec_name": "h264"},
            {"codec_type": "audio", "index": 1, "codec_name": "aac"},
        ],
        "format": {"format_name": "mpegts"},
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result1 = get_media_info(mock_path)

    # Simulate file modification by changing stat result
    mock_path.stat.return_value = MagicMock(st_mtime=678.90, st_size=12345)

    result2 = get_media_info(mock_path)

    # Assert
    assert result1 is not result2
    assert mock_execute_ffprobe.call_count == 2


@pytest.mark.integration
def test_get_media_info_integration(ts_file: Path) -> None:
    """Test that get_media_info works with a real ts file."""
    # Act
    result = get_media_info(ts_file)

    # Assert
    # Assuming a real ts file has at least one video and one audio stream at indices 0 and 1
    expected = MediaInfo(
        streams=(
            Stream(
                codec_type="video",
                index=0,
                codec_name="mpeg2video",
                profile="Main",
            ),
            Stream(
                codec_type="audio",
                index=1,
                codec_name="aac",
                profile="LC",
                channels=1,
                sample_rate=44100,
                bit_rate=5267,
            ),
            Stream(
                codec_type="audio",
                index=2,
                codec_name="aac",
                profile="LC",
                channels=1,
                sample_rate=44100,
                bit_rate=71510,
            ),
        ),
        format=Format(format_name="mpegts"),
    )

    assert result == expected
