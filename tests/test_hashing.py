from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.hashing import get_stream_md5


@pytest.mark.integration
def test_get_stream_md5(ts_file: Path) -> None:
    """Test the get_stream_md5 helper function."""
    expected_md5 = "9db9dd4cb46b9678894578946158955b"
    actual_md5 = get_stream_md5(ts_file, "a", 0)
    assert actual_md5 == expected_md5


@pytest.mark.unit
def test_get_stream_md5_failure(mocker: MockerFixture, ts_file: Path) -> None:
    """Test get_stream_md5 with a non-zero return code."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.hashing.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        get_stream_md5(ts_file, "a", 0)
