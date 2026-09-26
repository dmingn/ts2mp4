"""Builds FFmpeg arguments from stream sources."""

from pathlib import Path
from typing import assert_never

from .stream_disposition import build_disposition_args
from .stream_source import Conversion, Copy, EncodeAudio, EncodeVideo, StreamSources


def _encode_audio_args(conversion: EncodeAudio, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion``."""
    options: list[tuple[str, str | int | None]] = [
        ("codec", conversion.codec),
        ("ar", conversion.sample_rate),
        ("ac", conversion.channels),
        ("profile", conversion.profile),
        ("b", conversion.bit_rate),
        ("bsf", "aac_adtstoasc"),
    ]
    return [
        arg
        for name, value in options
        if value is not None
        for arg in (f"-{name}:{output_index}", str(value))
    ]


def _codec_args(conversion: Conversion, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream."""
    match conversion:
        case Copy():
            return [f"-codec:{output_index}", "copy"]
        case EncodeAudio():
            return _encode_audio_args(conversion, output_index)
        case EncodeVideo():
            raise NotImplementedError("Video encoding arguments are not supported.")
        case _ as unreachable:
            assert_never(unreachable)


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
        + build_disposition_args(stream_sources)
        + ["-f", "mp4", str(output_path)]
    )
