"""Unit and integration tests for the ffmpeg module."""

import io
import logging
from typing import AsyncGenerator, Optional, cast
from unittest.mock import AsyncMock, MagicMock

import logzero
import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import (
    FFmpegProcessError,
    FFmpegResult,
    _run_command,
    _stream_stdout,
    execute_ffmpeg,
    execute_ffmpeg_streamed,
    execute_ffprobe,
    is_libfdk_aac_available,
)


class MockAsyncProcess:
    """A mock asyncio.subprocess.Process."""

    stdout: Optional[MagicMock]
    stderr: Optional[MagicMock]

    def __init__(
        self,
        stdout_chunks: Optional[list[bytes]] = None,
        stderr_chunks: Optional[list[bytes]] = None,
        returncode: int = 0,
    ):
        self.stdout = self._mock_stream(stdout_chunks)
        self.stderr = self._mock_stream(stderr_chunks)
        self.returncode = returncode
        self.pid = 123
        self._wait_mock = AsyncMock(return_value=returncode)

    def _mock_stream(self, chunks: Optional[list[bytes]]) -> MagicMock:
        if chunks is None:
            chunks = []
        stream = MagicMock()
        stream.read = AsyncMock(side_effect=chunks + [b""])
        stream.readline = AsyncMock(side_effect=chunks + [b""])
        return stream

    async def wait(self) -> int:
        """Mock wait method."""
        return cast(int, await self._wait_mock())

    def terminate(self) -> None:
        """Mock terminate method."""
        pass


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ffmpeg_output", "expected"),
    [
        (b"... some encoders ...", False),
        (b"... libfdk_aac ...", True),
    ],
)
def test_is_libfdk_aac_available(
    mocker: MockerFixture, ffmpeg_output: bytes, expected: bool
) -> None:
    """Test that is_libfdk_aac_available returns the correct value."""
    is_libfdk_aac_available.cache_clear()
    mock_execute_ffmpeg = mocker.patch("ts2mp4.ffmpeg.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=ffmpeg_output, stderr="", returncode=0
    )

    assert is_libfdk_aac_available() is expected


@pytest.mark.unit
def test_is_libfdk_aac_available_caching(mocker: MockerFixture) -> None:
    """Test that is_libfdk_aac_available caches results."""
    is_libfdk_aac_available.cache_clear()
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.ffmpeg.execute_ffmpeg",
        return_value=FFmpegResult(stdout=b"libfdk_aac", stderr="", returncode=0),
    )

    # Call twice
    is_libfdk_aac_available()
    is_libfdk_aac_available()

    # Assert that execute_ffmpeg was only called once
    mock_execute_ffmpeg.assert_called_once()


@pytest.mark.integration
def test_execute_ffmpeg_success() -> None:
    """Test that execute_ffmpeg runs ffmpeg successfully."""
    result = execute_ffmpeg(["-version"])
    assert result.returncode == 0
    assert b"ffmpeg version" in result.stdout or "ffmpeg version" in result.stderr


@pytest.mark.integration
def test_execute_ffmpeg_failure() -> None:
    """Test that execute_ffmpeg returns a non-zero return code on failure."""
    result = execute_ffmpeg(["-invalid_option"])
    assert result.returncode != 0


@pytest.mark.integration
def test_execute_ffprobe_success() -> None:
    """Test that execute_ffprobe runs ffprobe successfully."""
    result = execute_ffprobe(["-version"])
    assert result.returncode == 0
    assert b"ffprobe version" in result.stdout or "ffprobe version" in result.stderr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handles_non_utf8_output_stream_stdout(mocker: MockerFixture) -> None:
    """Test that _stream_stdout handles non-UTF8 stderr correctly."""
    mock_process = MockAsyncProcess(returncode=0, stderr_chunks=[b"invalid byte: \xff"])
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)
    mock_logger_info = mocker.patch("logzero.logger.info")

    _ = [chunk async for chunk in _stream_stdout("ffmpeg", [])]

    mock_logger_info.assert_any_call("invalid byte: �")


@pytest.mark.unit
def test_handles_non_utf8_output_run_command(mocker: MockerFixture) -> None:
    """Test that _run_command handles non-UTF-8 output correctly."""
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_result = MagicMock()
    mock_result.stdout = b""
    mock_result.stderr = b"invalid byte: \xff"
    mock_result.returncode = 0
    mock_subprocess_run.return_value = mock_result

    result = _run_command("ffmpeg", [])
    assert "�" in result.stderr


@pytest.mark.integration
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_ffmpeg_streamed(mocker: MockerFixture) -> None:
    """Test that execute_ffmpeg_streamed calls _stream_stdout."""
    expected_args = ["-i", "input.ts", "output.mp4"]

    async def mock_stream_stdout(
        executable: str, args: list[str]
    ) -> AsyncGenerator[bytes, None]:
        assert executable == "ffmpeg"
        assert args == expected_args
        yield b"test"

    mocker.patch("ts2mp4.ffmpeg._stream_stdout", mock_stream_stdout)

    result = [chunk async for chunk in execute_ffmpeg_streamed(expected_args)]
    assert result == [b"test"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stdout_success(mocker: MockerFixture) -> None:
    """Test that _stream_stdout yields stdout chunks on success."""
    mock_process = MockAsyncProcess(stdout_chunks=[b"chunk1", b"chunk2"])
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    result = [chunk async for chunk in _stream_stdout("ffmpeg", [])]

    assert result == [b"chunk1", b"chunk2"]
    mock_process._wait_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stdout_failure(mocker: MockerFixture) -> None:
    """Test that _stream_stdout raises FFmpegProcessError on failure."""
    mock_process = MockAsyncProcess(returncode=1)
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    with pytest.raises(
        FFmpegProcessError,
        match="ffmpeg failed with exit code 1. Check logs for details.",
    ):
        _ = [chunk async for chunk in _stream_stdout("ffmpeg", [])]
    mock_process._wait_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stdout_no_stdout(mocker: MockerFixture) -> None:
    """Test that _stream_stdout raises error if stdout is None."""
    mock_process = MockAsyncProcess()
    mock_process.stdout = None
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    with pytest.raises(
        FFmpegProcessError, match="Failed to open stdout for the process."
    ):
        _ = [chunk async for chunk in _stream_stdout("ffmpeg", [])]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stdout_no_stderr(mocker: MockerFixture) -> None:
    """Test that _stream_stdout raises error if stderr is None."""
    mock_process = MockAsyncProcess()
    mock_process.stderr = None
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    with pytest.raises(
        FFmpegProcessError, match="Failed to open stderr for the process."
    ):
        _ = [chunk async for chunk in _stream_stdout("ffmpeg", [])]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stdout_ffmpeg_process_error(mocker: MockerFixture) -> None:
    """Test that _stream_stdout raises FFmpegProcessError on OSError."""
    mocker.patch("asyncio.create_subprocess_exec", side_effect=OSError("test error"))
    with pytest.raises(
        FFmpegProcessError, match="Failed to start ffmpeg process: test error"
    ):
        _ = [chunk async for chunk in _stream_stdout("ffmpeg", [])]
