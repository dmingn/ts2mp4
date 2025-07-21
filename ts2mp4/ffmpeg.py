import functools
import subprocess
from typing import Literal, NamedTuple

from logzero import logger


class FFmpegResult(NamedTuple):
    """A class to hold the results of an FFmpeg command."""

    stdout: bytes
    stderr: str
    returncode: int


def _execute_process(
    executable: Literal["ffmpeg", "ffprobe"], args: list[str]
) -> FFmpegResult:
    command = [executable] + args
    logger.info(f"Running command: {' '.join(command)}")

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr_bytes = process.communicate()

    # stdout is treated as binary data, as it can contain multimedia streams.
    # stderr is treated as text, as it's used for logs and progress information.
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if stderr:
        logger.info(stderr)

    return FFmpegResult(stdout=stdout, stderr=stderr, returncode=process.returncode)


def execute_ffmpeg(args: list[str]) -> FFmpegResult:
    """Execute ffmpeg and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns:
    -------
        An FFmpegResult object with the command's results.

    """
    return _execute_process("ffmpeg", args)


def execute_ffprobe(args: list[str]) -> FFmpegResult:
    """Execute ffprobe and returns the result.

    Args:
    ----
        args: A list of arguments for the command.

    Returns:
    -------
        An FFmpegResult object with the command's results.

    """
    return _execute_process("ffprobe", args)


@functools.cache
def is_libfdk_aac_available() -> bool:
    """Check if libfdk_aac is available in ffmpeg.

    Returns
    -------
        True if libfdk_aac is available, False otherwise.

    """
    result = execute_ffmpeg(["-encoders"])
    return b"libfdk_aac" in result.stdout
