"""A module for interacting with FFmpeg."""

import asyncio
import functools
import subprocess
from typing import AsyncGenerator, Literal, NamedTuple

from logzero import logger


class FFmpegProcessError(Exception):
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
    """
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    # Use check=False to prevent CalledProcessError on non-zero exit codes,
    # allowing us to read stderr for detailed FFmpeg error messages.
    process = subprocess.run(command, capture_output=True, check=False)

    stdout = process.stdout
    stderr = process.stderr.decode("utf-8", errors="replace")

    if stderr:
        logger.info(stderr)

    return FFmpegResult(stdout=stdout, stderr=stderr, returncode=process.returncode)


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
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise FFmpegProcessError(f"Failed to start {executable} process: {e}") from e

    if process.stdout is None:
        raise FFmpegProcessError("Failed to open stdout for the process.")
    if process.stderr is None:
        raise FFmpegProcessError("Failed to open stderr for the process.")

    stdout_stream = process.stdout
    stderr_stream = process.stderr

    async def log_stderr() -> None:
        """Read from stderr and log each line."""
        while line := await stderr_stream.readline():
            decoded_line = line.decode("utf-8", errors="replace").strip()
            logger.info(decoded_line)

    async def stream_stdout() -> AsyncGenerator[bytes, None]:
        """Read from stdout and yield chunks."""
        while chunk := await stdout_stream.read(1024):
            yield chunk

    log_task = asyncio.create_task(log_stderr())

    try:
        async for chunk in stream_stdout():
            yield chunk
    finally:
        await log_task

    returncode = await process.wait()

    if returncode != 0:
        raise FFmpegProcessError(
            f"{executable} failed with exit code {returncode}. Check logs for details."
        )


async def _stream_stderr(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> AsyncGenerator[str, None]:
    """Execute a process and yield its stderr line by line, while also logging it."""
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise FFmpegProcessError(f"Failed to start {executable} process: {e}") from e

    if process.stderr is None:
        raise FFmpegProcessError("Failed to open stderr for the process.")

    stderr_stream = process.stderr

    while line_bytes := await stderr_stream.readline():
        line_str = line_bytes.decode("utf-8", errors="replace")
        logger.info(line_str.strip())
        yield line_str

    returncode = await process.wait()

    if returncode != 0:
        raise FFmpegProcessError(
            f"{executable} failed with exit code {returncode}. Check logs for details."
        )


def execute_ffmpeg(args: list[str]) -> FFmpegResult:
    """Execute ffmpeg and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An FFmpegResult object with the command's results.

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
