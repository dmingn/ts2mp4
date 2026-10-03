"""Detects audio streams that must be re-encoded as fixed 5.1ch."""

from functools import cache

from .ffmpeg import execute_ffprobe
from .video_file import AudioStream, VideoFile

STEREO_CHANNELS = 2
SURROUND_5_1_CHANNELS = 6
SURROUND_5_1_LAYOUT = "5.1"
SUPPORTED_CHANNEL_COUNTS = frozenset({STEREO_CHANNELS, SURROUND_5_1_CHANNELS})


class UnsupportedChannelLayoutError(ValueError):
    """Raised when a stream with 5.1ch frames also has unsupported channel counts."""


@cache
def _get_frame_channel_counts_cached(
    stream: AudioStream, _mtime: float, _size: int
) -> frozenset[int]:
    """Return the channel counts of the decoded frames, cached per file state.

    ``_mtime`` and ``_size`` are cache invalidation keys only.
    """
    result = execute_ffprobe(
        [
            "-hide_banner",
            "-v",
            "error",
            "-select_streams",
            str(stream.index),
            "-show_entries",
            "frame=channels",
            "-of",
            "csv=p=0",
            str(stream.file.path),
        ]
    )

    return frozenset(
        int(line) for line in result.stdout.decode("utf-8").split() if line
    )


def get_frame_channel_counts(stream: AudioStream) -> frozenset[int]:
    """Return the set of channel counts found in the decoded frames of ``stream``.

    Raises
    ------
        FFmpegProcessError: If ffprobe fails to read the frames.
    """
    stat = stream.file.path.resolve(strict=True).stat()
    return _get_frame_channel_counts_cached(stream, stat.st_mtime, stat.st_size)


def requires_fixed_surround(declared: int | None, observed: frozenset[int]) -> bool:
    """Return True if a stream must be re-encoded as fixed 5.1ch.

    A stream requires it when its frames contain 5.1ch but the stream is not
    consistently 5.1ch, either because other channel counts are mixed in or
    because the declared channel count is not 5.1ch.

    Args:
    ----
        declared: The channel count declared by the container.
        observed: The channel counts found in the decoded frames.

    Raises
    ------
        UnsupportedChannelLayoutError: If ``observed`` contains 5.1ch and a
            channel count other than stereo and 5.1ch.
    """
    if SURROUND_5_1_CHANNELS not in observed:
        return False

    unsupported = observed - SUPPORTED_CHANNEL_COUNTS
    if unsupported:
        raise UnsupportedChannelLayoutError(
            f"Unsupported channel counts {sorted(unsupported)} are mixed with 5.1ch. "
            f"Only {sorted(SUPPORTED_CHANNEL_COUNTS)} are supported."
        )

    return observed != {SURROUND_5_1_CHANNELS} or declared != SURROUND_5_1_CHANNELS


def _stream_requires_fixed_surround(stream: AudioStream) -> bool:
    """Return True if ``stream`` must be re-encoded as fixed 5.1ch."""
    try:
        return requires_fixed_surround(
            stream.channels, get_frame_channel_counts(stream)
        )
    except UnsupportedChannelLayoutError as e:
        e.add_note(f"Audio stream at index {stream.index} in {stream.file.path}")
        raise


def find_streams_requiring_fixed_surround(file: VideoFile) -> frozenset[int]:
    """Return the indices of the audio streams in ``file`` to re-encode as fixed 5.1ch.

    Raises
    ------
        UnsupportedChannelLayoutError: If a stream mixes 5.1ch with an
            unsupported channel count.
    """
    return frozenset(
        stream.index
        for stream in file.valid_audio_streams
        if _stream_requires_fixed_surround(stream)
    )
