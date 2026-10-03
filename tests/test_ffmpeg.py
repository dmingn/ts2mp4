"""Unit and integration tests for the ffmpeg module."""

import io
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Optional, cast
from unittest.mock import AsyncMock, MagicMock

import logzero
import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.ffmpeg import (
    FFmpegProcessError,
    SubprocessFFmpegRunner,
    _parse_out_seconds,
    _run_command,
    _stream_out_seconds,
    _stream_stdout,
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
def test_is_libfdk_aac_available(ffmpeg_output: bytes, expected: bool) -> None:
    """Test that is_libfdk_aac_available returns the correct value."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stdout=ffmpeg_output)

    # Act
    result = is_libfdk_aac_available(ffmpeg_runner)

    # Assert
    assert result is expected


@pytest.mark.unit
def test_is_libfdk_aac_available_caching() -> None:
    """Test that is_libfdk_aac_available caches results."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stdout=b"libfdk_aac")

    # Act
    is_libfdk_aac_available(ffmpeg_runner)
    is_libfdk_aac_available(ffmpeg_runner)

    # Assert
    assert len(ffmpeg_runner.calls) == 1


@pytest.mark.integration
def test_subprocess_ffmpeg_runner_run_success() -> None:
    """Test that SubprocessFFmpegRunner.run runs ffmpeg successfully."""
    result = SubprocessFFmpegRunner().run(["-version"])
    assert result.returncode == 0
    assert b"ffmpeg version" in result.stdout or "ffmpeg version" in result.stderr


@pytest.mark.integration
def test_subprocess_ffmpeg_runner_run_raises_on_nonzero_exit() -> None:
    """Test that SubprocessFFmpegRunner.run raises FFmpegProcessError when ffmpeg fails."""
    # Act & Assert
    with pytest.raises(FFmpegProcessError):
        SubprocessFFmpegRunner().run(["-invalid_option"])


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


@pytest.mark.unit
def test_run_command_raises_on_nonzero_returncode(mocker: MockerFixture) -> None:
    """Test that _run_command raises FFmpegProcessError on non-zero return code."""
    # Arrange
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_result = MagicMock()
    mock_result.stdout = b""
    mock_result.stderr = b""
    mock_result.returncode = 1
    mock_subprocess_run.return_value = mock_result

    # Act & Assert
    with pytest.raises(
        FFmpegProcessError,
        match="ffmpeg failed with exit code 1. Check logs for details.",
    ):
        _run_command("ffmpeg", [])


@pytest.mark.integration
def test_subprocess_ffmpeg_runner_run_logs_stderr_as_info() -> None:
    """Test that SubprocessFFmpegRunner.run logs stderr as info even when ffmpeg fails."""
    # Arrange
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logzero.logger.addHandler(handler)
    logzero.logger.setLevel(logging.INFO)

    # Act
    with pytest.raises(FFmpegProcessError):
        SubprocessFFmpegRunner().run(["-invalid_option"])
    logzero.logger.removeHandler(handler)

    # Assert
    assert "Unrecognized option" in log_stream.getvalue()


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_out_seconds_requests_progress_on_stdout(
    mocker: MockerFixture,
) -> None:
    """_stream_out_seconds appends -progress pipe:1 to the arguments."""
    # Arrange
    mock_create_subprocess_exec = mocker.patch(
        "asyncio.create_subprocess_exec", return_value=MockAsyncProcess()
    )

    # Act
    _ = [seconds async for seconds in _stream_out_seconds("ffmpeg", ["-i", "in.ts"])]

    # Assert
    assert mock_create_subprocess_exec.call_args.args == (
        "ffmpeg",
        "-i",
        "in.ts",
        "-progress",
        "pipe:1",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_out_seconds_yields_out_seconds_from_stdout(
    mocker: MockerFixture,
) -> None:
    """_stream_out_seconds yields the output seconds parsed from stdout."""
    # Arrange
    mock_process = MockAsyncProcess(
        stdout_chunks=[b"out_time_us=1000000\n", b"speed=1x\n", b"progress=end\n"]
    )
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    # Act
    result = [seconds async for seconds in _stream_out_seconds("ffmpeg", [])]

    # Assert
    assert result == [1.0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_out_seconds_logs_stderr(mocker: MockerFixture) -> None:
    """_stream_out_seconds logs each stderr line."""
    # Arrange
    mock_process = MockAsyncProcess(stderr_chunks=[b"some warning\n"])
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)
    mock_logger_info = mocker.patch("logzero.logger.info")

    # Act
    _ = [seconds async for seconds in _stream_out_seconds("ffmpeg", [])]

    # Assert
    mock_logger_info.assert_any_call("some warning")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_out_seconds_does_not_log_stdout(mocker: MockerFixture) -> None:
    """_stream_out_seconds does not log the progress reports read from stdout."""
    # Arrange
    mock_process = MockAsyncProcess(
        stdout_chunks=[b"out_time_us=1000000\n", b"progress=end\n"]
    )
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)
    mock_logger_info = mocker.patch("logzero.logger.info")

    # Act
    _ = [seconds async for seconds in _stream_out_seconds("ffmpeg", [])]

    # Assert
    logged = [call.args[0] for call in mock_logger_info.call_args_list]
    assert not any("out_time_us" in message for message in logged)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_out_seconds_failure(mocker: MockerFixture) -> None:
    """_stream_out_seconds raises FFmpegProcessError on a non-zero exit code."""
    # Arrange
    mocker.patch(
        "asyncio.create_subprocess_exec", return_value=MockAsyncProcess(returncode=1)
    )

    # Act & Assert
    with pytest.raises(
        FFmpegProcessError,
        match="ffmpeg failed with exit code 1. Check logs for details.",
    ):
        _ = [seconds async for seconds in _stream_out_seconds("ffmpeg", [])]


async def _aiter(lines: Iterable[str]) -> AsyncIterator[str]:
    for line in lines:
        yield line


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_out_seconds_yields_seconds_of_each_report() -> None:
    """_parse_out_seconds yields out_time_us of each report in seconds."""
    # Arrange
    lines = [
        "frame=10\n",
        "out_time_us=1500000\n",
        "speed=1.5x\n",
        "progress=continue\n",
        "frame=20\n",
        "out_time_us=3000000\n",
        "speed=2x\n",
        "progress=end\n",
    ]

    # Act
    result = [seconds async for seconds in _parse_out_seconds(_aiter(lines))]

    # Assert
    assert result == [1.5, 3.0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_out_seconds_skips_na_reports() -> None:
    """_parse_out_seconds skips reports whose out_time_us is N/A."""
    # Arrange
    lines = [
        "out_time_us=N/A\n",
        "progress=continue\n",
        "out_time_us=1000000\n",
        "progress=continue\n",
    ]

    # Act
    result = [seconds async for seconds in _parse_out_seconds(_aiter(lines))]

    # Assert
    assert result == [1.0]
