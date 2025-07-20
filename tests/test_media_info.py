import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import Format, MediaInfo, Stream, get_media_info


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_media_info.cache_clear()


@pytest.mark.unit
def test_get_media_info_success(mocker: MockerFixture) -> None:
    """Test that get_media_info returns a MediaInfo object on success."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    file_path = Path("test.ts")
    ffprobe_output = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"format_name": "mpegts"},
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result = get_media_info(file_path)

    # Assert
    expected = MediaInfo(
        streams=(
            Stream(codec_type="video"),
            Stream(codec_type="audio"),
        ),
        format=Format(format_name="mpegts"),
    )
    assert result == expected
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.unit
def test_get_media_info_failure(mocker: MockerFixture) -> None:
    """Test that get_media_info raises a RuntimeError on ffprobe failure."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    file_path = Path("test.ts")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_execute_ffprobe.return_value = mock_result

    # Act & Assert
    with pytest.raises(RuntimeError):
        get_media_info(file_path)


@pytest.mark.unit
def test_get_media_info_invalid_json(mocker: MockerFixture) -> None:
    """Test that get_media_info raises a RuntimeError on invalid JSON."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    file_path = Path("test.ts")
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = b"invalid json"
    mock_execute_ffprobe.return_value = mock_result

    # Act & Assert
    with pytest.raises(json.JSONDecodeError):
        get_media_info(file_path)


@pytest.mark.unit
def test_get_media_info_ignores_unknown_fields(mocker: MockerFixture) -> None:
    """Test that get_media_info ignores unknown fields in the JSON output."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    file_path = Path("test.ts")
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
    result = get_media_info(file_path)

    # Assert
    expected = MediaInfo(
        streams=(),
        format=Format(format_name="test_format"),
    )
    assert result == expected
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.unit
def test_get_media_info_cached(mocker: MockerFixture) -> None:
    """Test that get_media_info caches the result."""
    # Arrange
    mock_execute_ffprobe = mocker.patch("ts2mp4.media_info.execute_ffprobe")
    file_path = Path("test.ts")
    ffprobe_output = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"format_name": "mpegts"},
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(ffprobe_output).encode("utf-8")
    mock_execute_ffprobe.return_value = mock_result

    # Act
    result1 = get_media_info(file_path)
    result2 = get_media_info(file_path)

    # Assert
    assert result1 is result2
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.integration
def test_get_media_info_integration(ts_file: Path) -> None:
    """Test that get_media_info works with a real ts file."""
    # Act
    result = get_media_info(ts_file)

    # Assert
    expected = MediaInfo(
        streams=(
            Stream(codec_type="video"),
            Stream(codec_type="audio"),
        ),
        format=Format(format_name="mpegts"),
    )

    assert result == expected
