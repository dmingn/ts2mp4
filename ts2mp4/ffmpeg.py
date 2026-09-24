"""A module for interacting with FFmpeg."""

import asyncio
import functools
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Literal, NamedTuple

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
    executable: Literal["ffmpeg", "ffprobe"], args: list[str], pipe_stdout: bool
) -> AsyncIterator[tuple[asyncio.StreamReader | None, asyncio.StreamReader]]:
    """Start a process and check its return code after the caller finishes reading.

    stderr is always piped. The return code is checked only when the caller's
    block exits normally.

    Args:
    ----
        executable: The FFmpeg or FFprobe executable.
        args: A list of arguments for the command.
        pipe_stdout: Whether to pipe stdout. If False, stdout is discarded.

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
            stdout=asyncio.subprocess.PIPE
            if pipe_stdout
            else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise FFmpegProcessError(f"Failed to start {executable} process: {e}") from e

    if pipe_stdout and process.stdout is None:
        raise FFmpegProcessError("Failed to open stdout for the process.")
    if process.stderr is None:
        raise FFmpegProcessError("Failed to open stderr for the process.")

    yield process.stdout, process.stderr

    returncode = await process.wait()

    if returncode != 0:
        raise FFmpegProcessError(
            f"{executable} failed with exit code {returncode}. Check logs for details."
        )


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
    async with _spawn(executable, args, pipe_stdout=True) as (
        stdout_stream,
        stderr_stream,
    ):
        assert stdout_stream is not None

        async def log_stderr() -> None:
            """Read from stderr and log each line."""
            while line := await stderr_stream.readline():
                decoded_line = line.decode("utf-8", errors="replace").strip()
                logger.info(decoded_line)

        log_task = asyncio.create_task(log_stderr())

        try:
            while chunk := await stdout_stream.read(1024):
                yield chunk
        finally:
            await log_task


async def _stream_stderr(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> AsyncGenerator[str, None]:
    """Execute a process and yield its stderr line by line, while also logging it."""
    async with _spawn(executable, args, pipe_stdout=False) as (
        _,
        stderr_stream,
    ):
        while line_bytes := await stderr_stream.readline():
            line_str = line_bytes.decode("utf-8", errors="replace")
            logger.info(line_str.strip())
            yield line_str


def execute_ffmpeg(args: list[str]) -> FFmpegResult:
    """Execute ffmpeg and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An FFmpegResult object with the command's results.

    Raises
    ------
        FFmpegProcessError: If ffmpeg exits with a non-zero return code.
    """
    return _run_command("ffmpeg", args)


async def execute_ffmpeg_streamed(
    args: list[str],
) -> AsyncGenerator[bytes, None]:
    """Execute ffmpeg and returns a generator for stdout.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An generator that yields stdout in chunks.
    """
    async for chunk in _stream_stdout("ffmpeg", args):
        yield chunk


async def execute_ffmpeg_stderr_streamed(args: list[str]) -> AsyncGenerator[str, None]:
    """Execute ffmpeg and returns a generator for stderr lines.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An generator that yields stderr lines.
    """
    async for line in _stream_stderr("ffmpeg", args):
        yield line


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
def is_libfdk_aac_available() -> bool:
    """Check if libfdk_aac is available in ffmpeg.

    Returns
    -------
        True if libfdk_aac is available, False otherwise.

    """
    result = execute_ffmpeg(["-encoders"])
    return b"libfdk_aac" in result.stdout
