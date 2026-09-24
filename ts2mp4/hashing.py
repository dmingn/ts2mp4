"""A module for calculating stream hashes."""

import asyncio
import hashlib
from functools import cache
from typing import assert_never

from .ffmpeg import execute_ffmpeg_streamed
from .video_file import AudioStream, VideoStream


async def _get_stream_md5_async(stream: VideoStream | AudioStream) -> str:
    match stream:
        case AudioStream():
            output_format = "s16le"
        case VideoStream():
            output_format = "rawvideo"
        case _ as unreachable:
            assert_never(unreachable)

    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-i",
        str(stream.file.path.resolve(strict=True)),
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
    stream: VideoStream | AudioStream,
    _mtime: float,
    _size: int,
) -> str:
    """Calculate the MD5 hash of a decoded stream, with caching.

    This function uses the ``@cache`` decorator to store the results of stream
    hashing. The ``_mtime`` and ``_size`` parameters, while not used directly in
    the function body, are crucial for the caching mechanism. They act as
    cache invalidation keys. If the file's modification time or size changes,
    the arguments to this function will be different, resulting in a cache
    miss and forcing a fresh hash calculation.

    Args:
    ----
        stream: The domain stream to hash.
        _mtime: The modification time of the file, used for cache invalidation.
        _size: The size of the file, used for cache invalidation.

    Returns
    -------
        The MD5 hash of the decoded stream as a hexadecimal string.
    """
    return asyncio.run(_get_stream_md5_async(stream))


def get_stream_md5(stream: VideoStream | AudioStream) -> str:
    """Calculate the MD5 hash of a decoded stream.

    Args:
    ----
        stream: The domain stream to hash.

    Returns
    -------
        The MD5 hash of the decoded stream as a hexadecimal string.

    Raises
    ------
        FFmpegProcessError: If ffmpeg fails to extract the stream.
    """
    resolved_path = stream.file.path.resolve(strict=True)
    stat = resolved_path.stat()
    return _get_stream_md5_cached(stream, stat.st_mtime, stat.st_size)
