from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.hashing import get_stream_md5
from ts2mp4.media_info import Stream


@pytest.mark.unit
def test_get_stream_md5_caching(mocker: MockerFixture) -> None:
    """Test that get_stream_md5 caches results."""
    file_path = Path("test.ts")
    stream = Stream(index=0, codec_type="video")

    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.hashing.execute_ffmpeg",
        return_value=FFmpegResult(stdout=b"stream_data", stderr="", returncode=0),
    )

    # Call twice
    get_stream_md5(file_path, stream)
    get_stream_md5(file_path, stream)

    # Assert that execute_ffmpeg was only called once
    mock_execute_ffmpeg.assert_called_once()


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
    stream = Stream(index=stream_index, codec_type=codec_type)
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
    mock_execute_ffmpeg = mocker.patch("ts2mp4.hashing.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )
    stream = Stream(index=stream_index, codec_type=codec_type)
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        get_stream_md5(ts_file, stream)
