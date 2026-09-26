"""Selects which output streams receive the MP4 `default` disposition."""

from collections.abc import Sequence

from .video_file import AudioStream, Stream, VideoStream

DEFAULT_STREAM_DURATION_RATIO = 0.9


def _spans_source_container(stream: Stream) -> bool:
    """Return True if the stream spans most of its source container.

    When the container duration is unavailable, the stream is treated as a
    candidate so that selection can fall back to other criteria. When the
    container duration is known but the stream duration is not, the stream is
    not treated as spanning — MPEG-TS remnants often lack end PTS and report
    no duration while the real program streams do.
    """
    container_duration = stream.file.duration
    stream_duration = stream.duration

    if container_duration is None or container_duration <= 0:
        return True
    if stream_duration is None:
        return False

    return stream_duration / container_duration >= DEFAULT_STREAM_DURATION_RATIO


def _video_pixel_count(stream: VideoStream) -> int:
    """Return the pixel count of a video stream, or 0 when unknown."""
    width = stream.width or 0
    height = stream.height or 0
    return width * height


def get_default_stream_indices(streams: Sequence[Stream]) -> frozenset[int]:
    """Return the positions in ``streams`` to mark with disposition default.

    For each of video and audio, the primary stream is the one that best spans
    its source container. Among video streams that tie on that criterion, the
    highest resolution wins. Ties are broken by the earlier position.
    """
    default_stream_indices: set[int] = set()

    video_candidates = [
        (i, stream)
        for i, stream in enumerate(streams)
        if isinstance(stream, VideoStream)
    ]
    if video_candidates:
        best_video_index, _ = max(
            video_candidates,
            key=lambda item: (
                _spans_source_container(item[1]),
                _video_pixel_count(item[1]),
                -item[0],
            ),
        )
        default_stream_indices.add(best_video_index)

    audio_candidates = [
        (i, stream)
        for i, stream in enumerate(streams)
        if isinstance(stream, AudioStream)
    ]
    if audio_candidates:
        best_audio_index, _ = max(
            audio_candidates,
            key=lambda item: (_spans_source_container(item[1]), -item[0]),
        )
        default_stream_indices.add(best_audio_index)

    return frozenset(default_stream_indices)
