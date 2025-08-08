"""A module for calculating stream hashes."""

import asyncio
import hashlib
from functools import cache
from pathlib import Path

from ts2mp4.media_info import Stream

from .ffmpeg import execute_ffmpeg_streamed


async def _get_stream_md5_async(
    file_path: Path, _mtime: float, _size: int, stream: Stream
) -> str:
    if stream.codec_type == "audio":
        output_format = "s16le"
    elif stream.codec_type == "video":
        output_format = "rawvideo"
    else:
        raise ValueError(
            f"Unsupported stream type for MD5 calculation: {stream.codec_type}. "
            "Only 'audio' and 'video' are supported."
        )

    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-i",
        str(file_path),
        "-map",
        f"0:{stream.index}",
        "-f",
        output_format,
        "-",  # Output to stdout
    ]

    process_generator = execute_ffmpeg_streamed(ffmpeg_args)
    md5_hash = hashlib.md5()
    async for chunk in process_generator:
        md5_hash.update(chunk)

    return md5_hash.hexdigest()


@cache
def _get_stream_md5_cached(
    file_path: Path, _mtime: float, _size: int, stream: Stream
) -> str:
    return asyncio.run(_get_stream_md5_async(file_path, _mtime, _size, stream))


def get_stream_md5(file_path: Path, stream: Stream) -> str:
    """Calculate the MD5 hash of a decoded stream of a given file.

    Args:
    ----
        file_path: The path to the input file.
        stream: The stream object to process.

    Returns
    -------
        The MD5 hash of the decoded stream as a hexadecimal string.

    Raises
    ------
        ValueError: If the stream type is unsupported.
        RuntimeError: If ffmpeg fails to extract the stream.

    """
    resolved_path = file_path.resolve(strict=True)
    stat = resolved_path.stat()
    return _get_stream_md5_cached(resolved_path, stat.st_mtime, stat.st_size, stream)
