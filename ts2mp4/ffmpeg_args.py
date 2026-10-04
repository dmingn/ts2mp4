"""Builds FFmpeg arguments from a file conversion plan."""

from pathlib import Path
from typing import assert_never

from .conversion_plan import (
    AudioEncodingMethod,
    BitRate,
    ConversionMethod,
    Copy,
    EncodeAudioWithLibfdkAac,
    EncodeAudioWithNativeAac,
    EncodeVideo,
    FileConversionPlan,
    LibfdkVbrMode,
)
from .ffmpeg_input_args import build_input_args


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
            ("pix_fmt", conversion_method.pix_fmt),
            ("filter", conversion_method.video_filter),
            ("fps_mode", conversion_method.fps_mode),
        ],
        output_index,
    )


def _rate_control_options(
    rate_control: BitRate | LibfdkVbrMode | None,
) -> list[tuple[str, str | int | None]]:
    """Build the options that set ``rate_control``."""
    match rate_control:
        case None:
            return []
        case BitRate():
            return [("b", rate_control.bit_rate)]
        case LibfdkVbrMode():
            return [("vbr", rate_control.mode)]
        case _ as unreachable:
            assert_never(unreachable)


def _encode_audio_args(
    conversion_method: AudioEncodingMethod, output_index: int
) -> list[str]:
    """Build the codec arguments for an output stream encoded with ``conversion_method``."""
    return _stream_options_args(
        [
            ("codec", conversion_method.codec),
            ("ar", conversion_method.sample_rate),
            ("ac", conversion_method.channels),
            ("profile", conversion_method.profile),
            *_rate_control_options(conversion_method.rate_control),
            ("filter", conversion_method.audio_filter),
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
        case EncodeAudioWithLibfdkAac() | EncodeAudioWithNativeAac():
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

    Output stream ``i`` is mapped from input ``i``, which reads the source file
    of ``file_conversion_plan[i]``. Each output stream gets its own input even
    when streams share a source file, because FFmpeg truncates the other
    decoded streams of an input when one of them ends midway.
    """
    return (
        ["-hide_banner", "-nostats", "-y"]
        + [
            arg
            for plan in file_conversion_plan
            for arg in build_input_args(plan.source_stream.file.path)
        ]
        + [
            arg
            for i, plan in enumerate(file_conversion_plan)
            for arg in (
                "-map",
                f"{i}:{plan.source_stream.index}",
                *_codec_args(plan.conversion_method, i),
            )
        ]
        + _disposition_args(file_conversion_plan)
        + ["-movflags", "+faststart", "-f", "mp4", str(output_path)]
    )
