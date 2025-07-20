from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.hashing import StreamType, get_stream_md5


@pytest.mark.integration
@pytest.mark.parametrize(
    "stream_type, expected_md5",
    [
        ("video", "df43568a405cdd212ef5ddc20da46416"),  # Video stream MD5
        ("audio", "9db9dd4cb46b9678894578946158955b"),  # Audio stream MD5
    ],
)
def test_get_stream_md5(
    ts_file: Path, stream_type: StreamType, expected_md5: str
) -> None:
    """Test the get_stream_md5 function for both video and audio streams."""
    actual_md5 = get_stream_md5(ts_file, stream_type, 0)
    assert actual_md5 == expected_md5


@pytest.mark.unit
@pytest.mark.parametrize(
    "stream_type",
    ["audio", "video"],
)
def test_get_stream_md5_failure(
    mocker: MockerFixture, ts_file: Path, stream_type: StreamType
) -> None:
    """Test get_stream_md5 with a non-zero return code."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.hashing.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        get_stream_md5(ts_file, stream_type, 0)
