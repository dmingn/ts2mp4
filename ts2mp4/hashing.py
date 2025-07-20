import hashlib
from pathlib import Path
from typing import Literal

from .ffmpeg import execute_ffmpeg

StreamType = Literal["audio", "video"]


def get_stream_md5(file_path: Path, stream_type: StreamType, stream_index: int) -> str:
    """Calculates the MD5 hash of a decoded stream of a given file.

    Args:
        file_path: The path to the input file.
        stream_type: The type of the stream to process ('audio' or 'video').
        stream_index: The index of the stream to process.

    Returns:
        The MD5 hash of the decoded stream as a hexadecimal string.

    Raises:
        RuntimeError: If ffmpeg fails to extract the stream.
    """
    if stream_type == "audio":
        map_specifier = f"0:a:{stream_index}"
        output_format = "s16le"
        stream_disabling_arg = "-vn"  # Disable video stream
    elif stream_type == "video":
        map_specifier = f"0:v:{stream_index}"
        output_format = "rawvideo"
        stream_disabling_arg = "-an"  # Disable audio stream
    else:
        raise ValueError(
            f"Invalid stream_type: {stream_type}. Must be 'audio' or 'video'."
        )

    ffmpeg_args = [
        "-hide_banner",
        "-i",
        str(file_path),
        stream_disabling_arg,
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
