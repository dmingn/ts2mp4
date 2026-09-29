"""Builds FFmpeg arguments from a file conversion plan."""

from pathlib import Path
from typing import assert_never

from .stream_source import (
    ConversionMethod,
    Copy,
    EncodeAudio,
    EncodeVideo,
    FileConversionPlan,
)


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


def _encode_video_args(conversion_method: EncodeVideo, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion_method``."""
    return _stream_options_args(
        [
            ("codec", conversion_method.codec),
            ("crf", conversion_method.crf),
            ("preset", conversion_method.preset),
            ("filter", conversion_method.video_filter),
            ("fps_mode", conversion_method.fps_mode),
        ],
        output_index,
    )


def _encode_audio_args(conversion_method: EncodeAudio, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion_method``."""
    return _stream_options_args(
        [
            ("codec", conversion_method.codec),
            ("ar", conversion_method.sample_rate),
            ("ac", conversion_method.channels),
            ("profile", conversion_method.profile),
            ("b", conversion_method.bit_rate),
        ],
        output_index,
    )


def _codec_args(conversion_method: ConversionMethod, output_index: int) -> list[str]:
    """Build the codec arguments for an output stream."""
    match conversion_method:
        case Copy():
            return [f"-codec:{output_index}", "copy"]
        case EncodeVideo():
            return _encode_video_args(conversion_method, output_index)
        case EncodeAudio():
            return _encode_audio_args(conversion_method, output_index)
        case _ as unreachable:
            assert_never(unreachable)


def _disposition_args(file_conversion_plan: FileConversionPlan) -> list[str]:
    """Build -disposition arguments from ``file_conversion_plan.default_stream_indices``.

    The streams at those indices are set to default, and the default is
    cleared on every other stream.
    """
    default_stream_indices = file_conversion_plan.default_stream_indices
    return [
        arg
        for i in range(len(file_conversion_plan))
        for arg in (
            f"-disposition:{i}",
            "default" if i in default_stream_indices else "0",
        )
    ]


def build_ffmpeg_args(
    file_conversion_plan: FileConversionPlan, output_path: Path
) -> list[str]:
    """Build FFmpeg arguments that write ``file_conversion_plan`` to ``output_path``.

    Output stream ``i`` is mapped from ``file_conversion_plan[i]``. Each distinct
    source file becomes one input, in order of first appearance.
    """
    input_files = list(
        dict.fromkeys(s.source_stream.file for s in file_conversion_plan)
    )
    input_index_by_file = {file: i for i, file in enumerate(input_files)}

    return (
        ["-hide_banner", "-nostats", "-fflags", "+discardcorrupt", "-y"]
        + [arg for file in input_files for arg in ("-i", str(file.path))]
        + [
            arg
            for i, plan in enumerate(file_conversion_plan)
            for arg in (
                "-map",
                f"{input_index_by_file[plan.source_stream.file]}:"
                f"{plan.source_stream.index}",
                *_codec_args(plan.conversion_method, i),
            )
        ]
        + _disposition_args(file_conversion_plan)
        + ["-f", "mp4", str(output_path)]
    )
