"""A module for interacting with FFmpeg."""

import asyncio
import functools
import os
import subprocess
from collections.abc import AsyncIterable, Hashable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Literal, NamedTuple, Protocol

from logzero import logger


class FFmpegProcessError(RuntimeError):
    """Custom exception for FFmpeg process errors."""


class FFmpegResult(NamedTuple):
    """A class to hold the results of an FFmpeg command."""

    stdout: bytes
    stderr: str
    returncode: int


def _run_command(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> FFmpegResult:
    """Execute a process and return its stdout, stderr, and return code.

    Args:
    ----
        executable: The FFmpeg or FFprobe executable.
        args: A list of arguments for the command.

    Returns
    -------
        FFmpegResult: An object containing the stdout, stderr, and return code of the process.

    Raises
    ------
        FFmpegProcessError: If the process exits with a non-zero return code.
    """
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    # Use check=False so stderr can be logged before raising on failure.
    process = subprocess.run(command, capture_output=True, check=False)

    stdout = process.stdout
    stderr = process.stderr.decode("utf-8", errors="replace")

    if stderr:
        logger.info(stderr)

    if process.returncode != 0:
        raise FFmpegProcessError(
            f"{executable} failed with exit code {process.returncode}. "
            "Check logs for details."
        )

    return FFmpegResult(stdout=stdout, stderr=stderr, returncode=process.returncode)


@asynccontextmanager
async def _spawn(
    executable: Literal["ffmpeg", "ffprobe"],
    args: list[str],
    stdin: int | None = None,
    stdout: int = asyncio.subprocess.DEVNULL,
) -> AsyncIterator[tuple[asyncio.StreamReader | None, asyncio.StreamReader]]:
    """Start a process and check its return code after the caller finishes reading.

    stderr is always piped. The return code is checked only when the caller's
    block exits normally.

    Args:
    ----
        executable: The FFmpeg or FFprobe executable.
        args: A list of arguments for the command.
        stdin: A file descriptor to read stdin from. If None, stdin is inherited.
        stdout: ``asyncio.subprocess.PIPE``, ``asyncio.subprocess.DEVNULL``, or
            a file descriptor to write stdout to.

    Yields
    ------
        A tuple of the stdout stream (``None`` unless piped) and the stderr stream.

    Raises
    ------
        FFmpegProcessError: If the process fails to start, if a requested pipe
            cannot be opened, or if the process exits with a non-zero code.
    """
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=stdin,
            stdout=stdout,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise FFmpegProcessError(f"Failed to start {executable} process: {e}") from e

    if stdout == asyncio.subprocess.PIPE and process.stdout is None:
        raise FFmpegProcessError("Failed to open stdout for the process.")
    if process.stderr is None:
        raise FFmpegProcessError("Failed to open stderr for the process.")

    yield process.stdout, process.stderr

    returncode = await process.wait()

    if returncode != 0:
        raise FFmpegProcessError(
            f"{executable} failed with exit code {returncode}. Check logs for details."
        )


async def _log_lines(stream: asyncio.StreamReader) -> None:
    """Read ``stream`` until EOF and log each line."""
    while line := await stream.readline():
        logger.info(line.decode("utf-8", errors="replace").strip())


async def _decode_lines(stream: asyncio.StreamReader) -> AsyncIterator[str]:
    """Yield each line of ``stream`` decoded as UTF-8."""
    while line := await stream.readline():
        yield line.decode("utf-8", errors="replace")


async def _log_and_decode_lines(stream: asyncio.StreamReader) -> AsyncIterator[str]:
    """Yield each line of ``stream`` decoded as UTF-8, while also logging it."""
    async for line in _decode_lines(stream):
        logger.info(line.strip())
        yield line


async def _parse_out_seconds(lines: AsyncIterable[str]) -> AsyncIterator[float]:
    """Yield how many seconds of output FFmpeg has written, from each ``-progress`` report.

    The value is ``out_time_us`` converted to seconds: the position in the output
    timeline, not the elapsed wall-clock time. Reports whose ``out_time_us`` is
    ``N/A`` are skipped.
    """
    async for line in lines:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value != "N/A":
            yield int(value) / 1_000_000


async def _stream_stdout(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> AsyncGenerator[bytes, None]:
    """Execute a process and yield its stdout in chunks.

    This function runs a command as a subprocess, yielding its standard output
    in 1KB chunks. Standard error is captured and logged internally.

    Args:
    ----
        executable: The FFmpeg or FFprobe executable.
        args: A list of arguments for the command.

    Yields
    ------
        bytes: Chunks of stdout from the process.

    Raises
    ------
        FFmpegProcessError: If the process fails to start or if the pipes cannot be opened.
    """
    async with _spawn(executable, args, stdout=asyncio.subprocess.PIPE) as (
        stdout_stream,
        stderr_stream,
    ):
        assert stdout_stream is not None

        log_task = asyncio.create_task(_log_lines(stderr_stream))

        try:
            while chunk := await stdout_stream.read(1024):
                yield chunk
        finally:
            await log_task


async def _stream_out_seconds(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> AsyncGenerator[float, None]:
    """Execute a process and yield how many seconds of output it has written.

    ``-progress pipe:1`` is appended to ``args`` so that progress reports are
    written to stdout, apart from stderr, which is logged internally.
    """
    async with _spawn(
        executable, args + ["-progress", "pipe:1"], stdout=asyncio.subprocess.PIPE
    ) as (
        stdout_stream,
        stderr_stream,
    ):
        assert stdout_stream is not None

        log_task = asyncio.create_task(_log_lines(stderr_stream))

        try:
            async for out_seconds in _parse_out_seconds(_decode_lines(stdout_stream)):
                yield out_seconds
        finally:
            await log_task


async def _stream_stderr(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> AsyncGenerator[str, None]:
    """Execute a process and yield its stderr line by line, while also logging it."""
    async with _spawn(executable, args) as (_, stderr_stream):
        async for line in _log_and_decode_lines(stderr_stream):
            yield line


async def _stream_stderr_piped(
    executable: Literal["ffmpeg", "ffprobe"],
    source_args: list[str],
    args: list[str],
) -> AsyncGenerator[str, None]:
    """Execute a process that reads the stdout of a source process as its stdin.

    The stderr of the process is yielded line by line and logged, and the stderr
    of the source process is logged. The return codes of both are checked.
    """
    read_fd, write_fd = os.pipe()

    async with AsyncExitStack() as stack:
        try:
            _, source_stderr_stream = await stack.enter_async_context(
                _spawn(executable, source_args, stdout=write_fd)
            )
            _, stderr_stream = await stack.enter_async_context(
                _spawn(executable, args, stdin=read_fd)
            )
        finally:
            os.close(read_fd)
            os.close(write_fd)

        log_task = asyncio.create_task(_log_lines(source_stderr_stream))

        try:
            async for line in _log_and_decode_lines(stderr_stream):
                yield line
        finally:
            await log_task


class FFmpegRunner(Hashable, Protocol):
    """Runs ffmpeg with the given arguments.

    Runners are hashable so that results can be cached per runner.
    """

    def run(self, args: list[str]) -> FFmpegResult:
        """Run ffmpeg and return its result."""
        ...

    def stream_stdout(self, args: list[str]) -> AsyncIterator[bytes]:
        """Run ffmpeg and yield its stdout in chunks."""
        ...

    def stream_stderr(self, args: list[str]) -> AsyncIterator[str]:
        """Run ffmpeg and yield its stderr line by line."""
        ...

    def stream_stderr_piped(
        self, source_args: list[str], args: list[str]
    ) -> AsyncIterator[str]:
        """Run ffmpeg reading the stdout of ffmpeg run with ``source_args``.

        Yield the stderr of the ffmpeg run with ``args`` line by line.
        """
        ...

    def stream_out_seconds(self, args: list[str]) -> AsyncIterator[float]:
        """Run ffmpeg and yield how many seconds of output it has written."""
        ...


class SubprocessFFmpegRunner:
    """Runs ffmpeg as a subprocess."""

    def run(self, args: list[str]) -> FFmpegResult:
        """Run ffmpeg and return its result."""
        return _run_command("ffmpeg", args)

    async def stream_stdout(self, args: list[str]) -> AsyncIterator[bytes]:
        """Run ffmpeg and yield its stdout in chunks."""
        async for chunk in _stream_stdout("ffmpeg", args):
            yield chunk

    async def stream_stderr(self, args: list[str]) -> AsyncIterator[str]:
        """Run ffmpeg and yield its stderr line by line."""
        async for line in _stream_stderr("ffmpeg", args):
            yield line

    async def stream_stderr_piped(
        self, source_args: list[str], args: list[str]
    ) -> AsyncIterator[str]:
        """Run ffmpeg reading the stdout of ffmpeg run with ``source_args``.

        Yield the stderr of the ffmpeg run with ``args`` line by line.
        """
        async for line in _stream_stderr_piped("ffmpeg", source_args, args):
            yield line

    async def stream_out_seconds(self, args: list[str]) -> AsyncIterator[float]:
        """Run ffmpeg and yield how many seconds of output it has written."""
        async for out_seconds in _stream_out_seconds("ffmpeg", args):
            yield out_seconds


def execute_ffprobe(args: list[str]) -> FFmpegResult:
    """Execute ffprobe and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An FFmpegResult object with the command's results.

    Raises
    ------
        FFmpegProcessError: If ffprobe exits with a non-zero return code.
    """
    return _run_command("ffprobe", args)


@functools.cache
def is_libfdk_aac_available(ffmpeg_runner: FFmpegRunner) -> bool:
    """Check if libfdk_aac is available in ffmpeg.

    Args:
    ----
        ffmpeg_runner: The FFmpegRunner used to list the encoders.

    Returns
    -------
        True if libfdk_aac is available, False otherwise.

    """
    result = ffmpeg_runner.run(["-encoders"])
    return b"libfdk_aac" in result.stdout
