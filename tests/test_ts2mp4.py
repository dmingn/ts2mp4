from pathlib import Path

from ts2mp4.ts2mp4 import _get_audio_stream_md5

# Define paths relative to the project root
PROJECT_ROOT = Path(__file__).parent.parent
TS_FILE = PROJECT_ROOT / "tests" / "assets" / "test_video.ts"


def test_get_audio_stream_md5():
    """Test the _get_audio_stream_md5 helper function."""
    expected_md5 = "9db9dd4cb46b9678894578946158955b"
    actual_md5 = _get_audio_stream_md5(TS_FILE)
    assert actual_md5 == expected_md5
