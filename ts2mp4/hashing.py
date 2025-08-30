"""A module for calculating stream hashes."""

import asyncio
import hashlib
from functools import cache
from pathlib import Path
from typing import assert_never

from ts2mp4.media_info import AudioStream, VideoStream

from .ffmpeg import execute_ffmpeg_streamed


async def _get_stream_md5_async(
    file_path: Path, stream: VideoStream | AudioStream
) -> str:
    match stream.codec_type:
        case "audio":
            output_format = "s16le"
        case "video":
            output_format = "rawvideo"
        case _ as unreachable:
            assert_never(unreachable)

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
    file_path: Path, _mtime: float, _size: int, stream: VideoStream | AudioStream
) -> str:
    """Calculate the MD5 hash of a decoded stream, with caching.

    This function uses the `@cache` decorator to store the results of stream
    hashing. The `_mtime` and `_size` parameters, while not used directly in
    the function body, are crucial for the caching mechanism. They act as
    cache invalidation keys. If the file's modification time or size changes,
    the arguments to this function will be different, resulting in a cache
    miss and forcing a fresh hash calculation.

    Args:
    ----
        file_path: The path to the input file.
        _mtime: The modification time of the file, used for cache invalidation.
        _size: The size of the file, used for cache invalidation.
        stream: The stream object to process.

    Returns
    -------
        The MD5 hash of the decoded stream as a hexadecimal string.

    """
    return asyncio.run(_get_stream_md5_async(file_path, stream))


def get_stream_md5(file_path: Path, stream: VideoStream | AudioStream) -> str:
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
