import hashlib
from pathlib import Path
from typing import Literal

from .ffmpeg import execute_ffmpeg


def get_stream_md5(
    file_path: Path, stream_type: Literal["a", "v"], stream_index: int
) -> str:
    """Calculates the MD5 hash of a decoded stream of a given file.

    Args:
        file_path: The path to the input file.
        stream_type: The type of the stream to process ('a' for audio, 'v' for video).
        stream_index: The index of the stream to process.

    Returns:
        The MD5 hash of the decoded stream as a hexadecimal string.

    Raises:
        RuntimeError: If ffmpeg fails to extract the stream.
    """
    map_specifier = f"0:{stream_type}:{stream_index}"
    output_format = "s16le" if stream_type == "a" else "rawvideo"

    ffmpeg_args = [
        "-hide_banner",
        "-i",
        str(file_path),
        "-map",
        map_specifier,
        "-f",
        output_format,
        "-",  # Output to stdout
    ]
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to get decoded {stream_type} stream for {file_path}. "
            f"Return code: {result.returncode}"
        )
    return hashlib.md5(result.stdout).hexdigest()
