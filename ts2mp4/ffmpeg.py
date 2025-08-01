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


def _execute_process(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> Generator[bytes, None, tuple[int, str]]:
    """Execute a process and yield its stdout in chunks.

    Yields
    ------
        bytes: Chunks of stdout from the process.

    Returns
    -------
        tuple[int, str]: A tuple containing the return code and stderr of the process.

    Raises
    ------
        FFmpegProcessError: If stdout or stderr pipes cannot be opened.
    """
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


def _consume_process_generator(
    process_generator: Generator[bytes, None, tuple[int, str]],
) -> FFmpegResult:
    """Consumes a process generator, collects stdout, and returns an FFmpegResult."""
    stdout_chunks = []
    try:
        while True:
            stdout_chunks.append(next(process_generator))
    except StopIteration as e:
        returncode, stderr = e.value
    stdout = b"".join(stdout_chunks)
    return FFmpegResult(stdout=stdout, stderr=stderr, returncode=returncode)


def execute_ffmpeg(args: list[str]) -> FFmpegResult:
    """Execute ffmpeg and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An FFmpegResult object with the command's results.

    """
    process_generator = _execute_process("ffmpeg", args)
    return _consume_process_generator(process_generator)


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
    return _execute_process("ffmpeg", args)


def execute_ffprobe(args: list[str]) -> FFmpegResult:
    """Execute ffprobe and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns
    -------
        An FFmpegResult object with the command's results.

    """
    process_generator = _execute_process("ffprobe", args)
    return _consume_process_generator(process_generator)


@functools.cache
def is_libfdk_aac_available() -> bool:
    """Check if libfdk_aac is available in ffmpeg.

    Returns
    -------
        True if libfdk_aac is available, False otherwise.

    """
    result = execute_ffmpeg(["-encoders"])
    return b"libfdk_aac" in result.stdout
