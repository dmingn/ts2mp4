"""A module for calculating per-frame hashes of streams."""

import asyncio
from fractions import Fraction
from functools import cache

from pydantic import BaseModel, ConfigDict

from .ffmpeg import FFmpegRunner
from .ffmpeg_input_args import build_zero_based_input_args
from .video_file import AudioStream, SubtitleStream, VideoStream

_TIME_BASE_PREFIX = "#tb 0: "

HashableStream = VideoStream | AudioStream | SubtitleStream


class FrameHash(BaseModel):
    """The timestamp and MD5 hash of one frame."""

    pts: float
    md5: str

    model_config = ConfigDict(frozen=True)


def parse_framemd5(lines: list[str]) -> tuple[FrameHash, ...]:
    """Parse the output of FFmpeg's ``framemd5`` muxer for a single stream.

    Timestamps are converted from the stream time base into seconds. Columns
    after the hash, such as the side data of a packet, are ignored.
    """
    time_base = next(
        Fraction(line.removeprefix(_TIME_BASE_PREFIX))
        for line in lines
        if line.startswith(_TIME_BASE_PREFIX)
    )

    rows = (
        [field.strip() for field in line.split(",")]
        for line in lines
        if line.strip() and not line.startswith("#")
    )
    return tuple(
        FrameHash(pts=float(int(pts) * time_base), md5=md5)
        for _stream, _dts, pts, _duration, _size, md5, *_side_data in rows
    )


def _hashing_args(stream: HashableStream) -> list[str]:
    """Return the ffmpeg arguments that select what of ``stream`` is hashed.

    Video and audio frames are hashed after decoding. Subtitle streams have no
    decoder for some codecs, such as ARIB captions, so their packets are hashed
    as they are.
    """
    match stream:
        case SubtitleStream():
            return ["-codec", "copy"]
        case VideoStream() | AudioStream():
            return [
                "-fps_mode",
                "passthrough",
                # Video timestamps are otherwise rounded to the frame rate.
                "-enc_time_base:v",
                "demux",
            ]


async def _get_frame_hashes_async(
    stream: HashableStream, ffmpeg_runner: FFmpegRunner
) -> tuple[FrameHash, ...]:
    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-copyts",
        *build_zero_based_input_args(stream.file.path, stream.file.start_time),
        "-map",
        f"0:{stream.index}",
        *_hashing_args(stream),
        "-f",
        "framemd5",
        "-",  # Output to stdout
    ]

    output = b"".join(
        [chunk async for chunk in ffmpeg_runner.stream_stdout(ffmpeg_args)]
    )
    return parse_framemd5(output.decode("utf-8").splitlines())


@cache
def _get_frame_hashes_cached(
    stream: HashableStream,
    _mtime: float,
    _size: int,
    ffmpeg_runner: FFmpegRunner,
) -> tuple[FrameHash, ...]:
    """Calculate the per-frame hashes of a stream, with caching.

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
        ffmpeg_runner: The FFmpegRunner used to read the stream.

    Returns
    -------
        The timestamp and MD5 hash of each frame.
    """
    return asyncio.run(_get_frame_hashes_async(stream, ffmpeg_runner))


def get_frame_hashes(
    stream: HashableStream, ffmpeg_runner: FFmpegRunner
) -> tuple[FrameHash, ...]:
    """Calculate the timestamp and MD5 hash of each frame of a stream.

    Timestamps are in seconds from the start of the file.

    Args:
    ----
        stream: The domain stream to hash.
        ffmpeg_runner: The FFmpegRunner used to read the stream.

    Returns
    -------
        The timestamp and MD5 hash of each frame.

    Raises
    ------
        FFmpegProcessError: If ffmpeg fails to read the stream.
    """
    resolved_path = stream.file.path.resolve(strict=True)
    stat = resolved_path.stat()
    return _get_frame_hashes_cached(stream, stat.st_mtime, stat.st_size, ffmpeg_runner)
