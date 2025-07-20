from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.hashing import StreamType, get_stream_md5


@pytest.mark.integration
@pytest.mark.parametrize(
    "stream_type",
    ["video", "audio"],
)
def test_get_stream_md5(ts_file: Path, stream_type: StreamType) -> None:
    """Test the get_stream_md5 function for both video and audio streams."""
    actual_md5 = get_stream_md5(ts_file, stream_type, 0)
    # Check if the returned MD5 hash is a valid 32-character hexadecimal string
    assert len(actual_md5) == 32
    assert all(c in "0123456789abcdef" for c in actual_md5)


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
