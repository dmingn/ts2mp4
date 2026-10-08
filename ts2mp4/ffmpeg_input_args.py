"""Builds the arguments that open a file as an FFmpeg or FFprobe input."""

from pathlib import Path

# Broadcast TS files may carry streams whose parameters only appear well after
# the start, which the default probe window (5 MB / 5 s) misses. FFprobe and
# FFmpeg must use the same window so that they see the same streams.
_PROBE_ARGS = ("-analyzeduration", "100M", "-probesize", "100M")


def build_input_args(path: Path) -> list[str]:
    """Return the arguments that open ``path`` as an FFmpeg or FFprobe input."""
    return [*_PROBE_ARGS, "-i", str(path)]


def build_zero_based_input_args(path: Path, start_time: float | None) -> list[str]:
    """Return the arguments that open ``path`` as an FFmpeg input starting at zero.

    ``start_time`` is the start time of the file. The arguments must be used
    with ``-copyts``. Without it, FFmpeg shifts each input so that its own
    mapped streams start at zero, which discards the offsets between the
    streams of the file.
    """
    offset_args = ["-itsoffset", str(-start_time)] if start_time else []
    return offset_args + build_input_args(path)
