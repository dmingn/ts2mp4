"""Shared test helpers."""

from ts2mp4.video_file import Stream


def stream_at(streams: frozenset[Stream], index: int) -> Stream:
    """Return the stream whose index matches ``index``."""
    return next(stream for stream in streams if stream.index == index)
