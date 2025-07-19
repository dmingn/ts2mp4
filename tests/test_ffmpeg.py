import io
import logging
from unittest.mock import MagicMock

import logzero
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import execute_ffmpeg, execute_ffprobe


def test_execute_ffmpeg_success() -> None:
    """Test that execute_ffmpeg runs ffmpeg successfully."""
    result = execute_ffmpeg(["-version"])
    assert result.returncode == 0
    assert b"ffmpeg version" in result.stdout or "ffmpeg version" in result.stderr


def test_execute_ffmpeg_failure() -> None:
    """Test that execute_ffmpeg returns a non-zero return code on failure."""
    result = execute_ffmpeg(["-invalid_option"])
    assert result.returncode != 0


def test_execute_ffprobe_success() -> None:
    """Test that execute_ffprobe runs ffprobe successfully."""
    result = execute_ffprobe(["-version"])
    assert result.returncode == 0
    assert b"ffprobe version" in result.stdout or "ffprobe version" in result.stderr


def test_handles_non_utf8_output(mocker: MockerFixture) -> None:
    """Test that _execute_process handles non-UTF-8 output correctly."""
    mock_popen = mocker.patch("subprocess.Popen")
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"", b"invalid byte: \xff")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    from ts2mp4.ffmpeg import _execute_process

    result = _execute_process("ffmpeg", [])
    assert "�" in result.stderr


def test_logs_stderr_as_info() -> None:
    """Test that the execution logs stderr as info."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logzero.logger.addHandler(handler)
    logzero.logger.setLevel(logging.INFO)

    execute_ffmpeg(["-invalid_option"])

    logzero.logger.removeHandler(handler)
    log_contents = log_stream.getvalue()
    assert "Unrecognized option" in log_contents
