import hashlib
from pathlib import Path

from .ffmpeg import execute_ffmpeg
from .media_info import get_media_info


def get_stream_md5(file_path: Path, stream_index: int) -> str:
    """Calculate the MD5 hash of a decoded stream of a given file using its stream index.

    Args:
    ----
        file_path: The path to the input file.
        stream_index: The 0-based index of the stream to process within the file.

    Returns:
    -------
        The MD5 hash of the decoded stream as a hexadecimal string.

    Raises:
    ------
        ValueError: If the stream index is invalid or the stream type is unsupported.
        RuntimeError: If ffmpeg fails to extract the stream.

    """
    media_info = get_media_info(file_path)

    if stream_index >= len(media_info.streams) or stream_index < 0:
        raise ValueError(f"Invalid stream index: {stream_index}")

    stream = media_info.streams[stream_index]

    if stream.codec_type == "audio":
        output_format = "s16le"
        stream_disabling_arg = "-vn"  # Disable video stream
    elif stream.codec_type == "video":
        output_format = "rawvideo"
        stream_disabling_arg = "-an"  # Disable audio stream
    else:
        raise ValueError(
            f"Unsupported stream type for MD5 calculation: {stream.codec_type}. "
            "Only 'audio' and 'video' are supported."
        )

    ffmpeg_args = [
        "-hide_banner",
        "-i",
        str(file_path),
        stream_disabling_arg,
        "-map",
        f"0:{stream_index}",
        "-f",
        output_format,
        "-",  # Output to stdout
    ]
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to get decoded {stream.codec_type} stream for {file_path}. "
            f"Return code: {result.returncode}"
        )
    return hashlib.md5(result.stdout).hexdigest()
