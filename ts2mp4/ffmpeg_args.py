"""Builds FFmpeg arguments from stream sources."""

from pathlib import Path
from typing import assert_never

from .stream_source import Conversion, Copy, EncodeAudio, EncodeVideo, StreamSources


def _stream_options_args(
    options: list[tuple[str, str | int | None]], output_index: int
) -> list[str]:
    """Build per-stream option arguments, omitting options that are None."""
    return [
        arg
        for name, value in options
        if value is not None
        for arg in (f"-{name}:{output_index}", str(value))
    ]


def _encode_video_args(conversion: EncodeVideo, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion``."""
    return _stream_options_args(
        [
            ("codec", conversion.codec),
            ("crf", conversion.crf),
            ("preset", conversion.preset),
            ("filter", conversion.video_filter),
            ("fps_mode", conversion.fps_mode),
        ],
        output_index,
    )


def _encode_audio_args(conversion: EncodeAudio, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion``."""
    return _stream_options_args(
        [
            ("codec", conversion.codec),
            ("ar", conversion.sample_rate),
            ("ac", conversion.channels),
            ("profile", conversion.profile),
            ("b", conversion.bit_rate),
        ],
        output_index,
    )


def _codec_args(conversion: Conversion, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream."""
    match conversion:
        case Copy():
            return [f"-codec:{output_index}", "copy"]
        case EncodeVideo():
            return _encode_video_args(conversion, output_index)
        case EncodeAudio():
            return _encode_audio_args(conversion, output_index)
        case _ as unreachable:
            assert_never(unreachable)


def _disposition_args(stream_sources: StreamSources) -> list[str]:
    """Build -disposition arguments from ``stream_sources.default_stream_indices``.

    The streams at those indices are set to default, and the default is
    cleared on every other stream.
    """
    default_stream_indices = stream_sources.default_stream_indices
    return [
        arg
        for i in range(len(stream_sources))
        for arg in (
            f"-disposition:{i}",
            "default" if i in default_stream_indices else "0",
        )
    ]


def build_ffmpeg_args(stream_sources: StreamSources, output_path: Path) -> list[str]:
    """Build FFmpeg arguments that write ``stream_sources`` to ``output_path``.

    Output stream ``i`` is mapped from ``stream_sources[i]``. Each distinct
    source file becomes one input, in order of first appearance.
    """
    input_files = list(dict.fromkeys(s.source_stream.file for s in stream_sources))
    input_index_by_file = {file: i for i, file in enumerate(input_files)}

    return (
        ["-hide_banner", "-nostats", "-fflags", "+discardcorrupt", "-y"]
        + [arg for file in input_files for arg in ("-i", str(file.path))]
        + [
            arg
            for i, source in enumerate(stream_sources)
            for arg in (
                "-map",
                f"{input_index_by_file[source.source_stream.file]}:"
                f"{source.source_stream.index}",
                *_codec_args(source.conversion, i),
            )
        ]
        + _disposition_args(stream_sources)
        + ["-f", "mp4", str(output_path)]
    )
