"""A module for interacting with FFmpeg."""

import functools
import subprocess
from typing import Generator, Literal, NamedTuple

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
    """Execute a process and return its stdout, stderr, and return code."""
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


def _stream_command(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> Generator[bytes, None, tuple[int, str]]:
    """Execute a process and yield its stdout in chunks."""
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if process.stdout is None or process.stderr is None:
        raise FFmpegProcessError("Failed to open stdout/stderr for the process.")

    while chunk := process.stdout.read(1024):
        yield chunk

    stderr_bytes = process.stderr.read()

    # stdout is treated as binary data, as it can contain multimedia streams.
    # stderr is treated as text, as it's used for logs and progress information.
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if stderr:
        logger.info(stderr)

    process.wait()
    return process.returncode, stderr


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


def execute_ffmpeg_streamed(
    args: list[str],
) -> Generator[bytes, None, tuple[int, str]]:
    """Execute ffmpeg and returns a generator for stdout.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        A generator that yields stdout in chunks.
        The generator's return value is a tuple of (returncode, stderr).
    """
    return _stream_command("ffmpeg", args)


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
