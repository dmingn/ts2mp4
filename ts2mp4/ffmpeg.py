import subprocess
from typing import Literal, NamedTuple

from logzero import logger


class FFmpegResult(NamedTuple):
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
    """
    Executes ffmpeg and returns the result.

    Args:
        args: A list of arguments for the command.

    Returns:
        An FFmpegResult object with the command's results.
    """
    return _execute_process("ffmpeg", args)


def execute_ffprobe(args: list[str]) -> FFmpegResult:
    """
    Executes ffprobe and returns the result.

    Args:
        args: A list of arguments for the command.

    Returns:
        An FFmpegResult object with the command's results.
    """
    return _execute_process("ffprobe", args)
