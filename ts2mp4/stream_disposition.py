"""Selects which output streams receive the MP4 `default` disposition."""

from .media_info import Stream, VideoStream
from .video_file import (
    ConversionType,
    StreamSource,
    StreamSources,
    VideoFile,
    is_audio_stream_source,
    is_video_stream_source,
)

DEFAULT_STREAM_DURATION_RATIO = 0.9


def _spans_source_container(
    source: StreamSource[Stream, ConversionType],
) -> bool:
    """Return True if the stream spans most of its source container.

    When the container duration is unavailable, the stream is treated as a
    candidate so that selection can fall back to other criteria. When the
    container duration is known but the stream duration is not, the stream is
    not treated as spanning — MPEG-TS remnants often lack end PTS and report
    no duration while the real program streams do.
    """
    media_info = VideoFile(path=source.source_video_path).media_info
    container_duration = (
        media_info.format.duration if media_info.format is not None else None
    )
    stream_duration = source.source_stream.duration

    if container_duration is None or container_duration <= 0:
        return True
    if stream_duration is None:
        return False

    return stream_duration / container_duration >= DEFAULT_STREAM_DURATION_RATIO


def _video_pixel_count(source: StreamSource[VideoStream, ConversionType]) -> int:
    """Return the pixel count of a video stream source, or 0 when unknown."""
    width = source.source_stream.width or 0
    height = source.source_stream.height or 0
    return width * height


def get_default_stream_indices(stream_sources: StreamSources) -> frozenset[int]:
    """Return the output stream indices to mark with disposition default.

    For each of video and audio, the primary stream is the one that best spans
    the source container. Among video streams that tie on that criterion, the
    highest resolution wins. Ties are broken by the earlier output index.
    """
    default_stream_indices: set[int] = set()

    video_candidates: list[tuple[int, StreamSource[VideoStream, ConversionType]]] = [
        (i, source)
        for i, source in enumerate(stream_sources)
        if is_video_stream_source(source)
    ]
    if video_candidates:
        best_video_index, _ = max(
            video_candidates,
            key=lambda item: (
                _spans_source_container(item[1]),
                _video_pixel_count(item[1]),
            ),
        )
        default_stream_indices.add(best_video_index)

    audio_candidates = [
        (i, source)
        for i, source in enumerate(stream_sources)
        if is_audio_stream_source(source)
    ]
    if audio_candidates:
        best_audio_index, _ = max(
            audio_candidates,
            key=lambda item: (_spans_source_container(item[1]),),
        )
        default_stream_indices.add(best_audio_index)

    return frozenset(default_stream_indices)


def build_disposition_args(stream_sources: StreamSources) -> list[str]:
    """Build FFmpeg args marking only the primary video and audio stream as default."""
    default_stream_indices = get_default_stream_indices(stream_sources)
    args: list[str] = []
    for i in range(len(stream_sources)):
        args.extend(
            [
                f"-disposition:{i}",
                "default" if i in default_stream_indices else "0",
            ]
        )
    return args
