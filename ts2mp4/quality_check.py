"""A module for checking the quality of audio streams."""

import asyncio
import re
from itertools import zip_longest
from typing import AsyncIterable, NamedTuple

from logzero import logger

from .conversion_plan import EncodeAudio, FileConversionPlan
from .converted_video_file import ConvertedVideoFile
from .ffmpeg import FFmpegProcessError, FFmpegRunner
from .ffmpeg_input_args import build_input_args


class AudioQualityMetrics(NamedTuple):
    """Per-channel audio quality metrics of each segment.

    FFmpeg reports the metrics each time the filtergraph is configured, and it
    reconfigures the filtergraph when the input channel layout changes. Each
    segment therefore covers a span with one channel layout.
    """

    apsnr: tuple[tuple[float, ...], ...]  # Average Peak Signal-to-Noise Ratio
    asdr: tuple[tuple[float, ...], ...]  # Average Signal-to-Distortion Ratio


_METRIC_LINE_PATTERN = re.compile(
    r"\[Parsed_(?P<metric>apsnr|asdr)_\d+ @ [^\]]+\] (?:PSNR|SDR) "
    r"ch(?P<channel>\d+): "
    r"(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|-?inf|-?nan) dB"
)


async def parse_audio_quality_metrics(
    output_lines: AsyncIterable[str],
) -> AudioQualityMetrics:
    """Parse the APSNR and ASDR of every segment and channel from FFmpeg output.

    A ``ch0`` line starts a new segment of its metric.
    """
    segments: dict[str, list[list[float]]] = {"apsnr": [], "asdr": []}

    async for line in output_lines:
        match = _METRIC_LINE_PATTERN.search(line)
        if match is None:
            if "Parsed_apsnr" in line or "Parsed_asdr" in line:
                logger.warning(f"Could not parse audio quality metric from: {line}")
            continue

        metric_segments = segments[match["metric"]]
        if match["channel"] == "0" or not metric_segments:
            metric_segments.append([])
        metric_segments[-1].append(float(match["value"]))

    return AudioQualityMetrics(
        apsnr=tuple(tuple(segment) for segment in segments["apsnr"]),
        asdr=tuple(tuple(segment) for segment in segments["asdr"]),
    )


def format_audio_quality_segments(metrics: AudioQualityMetrics) -> tuple[str, ...]:
    """Return a description of each segment, such as ``APSNR=[30.00, 31.00]dB``."""
    return tuple(
        " ".join(
            f"{name}=[{', '.join(f'{value:.2f}' for value in values)}]dB"
            for name, values in (("APSNR", apsnr), ("ASDR", asdr))
            if values
        )
        for apsnr, asdr in zip_longest(metrics.apsnr, metrics.asdr, fillvalue=())
    )


def build_quality_filter_complex(
    original_input: str, re_encoded_input: str, audio_filter: str | None
) -> str:
    """Build the filtergraph that compares an original and a re-encoded stream.

    ``audio_filter`` is applied to the original stream so that it has the same
    channel layout as the re-encoded stream.
    """
    return ";".join(
        f"{original_input}{audio_filter}[original_{metric}];"
        f"[original_{metric}]{re_encoded_input}{metric}"
        if audio_filter is not None
        else f"{original_input}{re_encoded_input}{metric}"
        for metric in ("apsnr", "asdr")
    )


async def get_audio_quality_metrics(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> dict[int, AudioQualityMetrics]:
    """Calculate audio quality metrics for all converted audio streams.

    Args:
    ----
        converted_file: The converted video file.
        ffmpeg_runner: The FFmpegRunner used to compare the audio streams.

    Returns
    -------
        A dictionary mapping the output audio stream index to its quality metrics.
    """
    quality_metrics: dict[int, AudioQualityMetrics] = {}

    for stream_with_conversion_plan in converted_file.streams_with_conversion_plans:
        conversion_method = (
            stream_with_conversion_plan.conversion_plan.conversion_method
        )
        if not isinstance(conversion_method, EncodeAudio):
            continue

        original_file = (
            stream_with_conversion_plan.conversion_plan.source_stream.file.path
        )
        re_encoded_file = converted_file.path
        original_stream_index = (
            stream_with_conversion_plan.conversion_plan.source_stream.index
        )
        re_encoded_stream_index = stream_with_conversion_plan.stream.index

        command = [
            "-hide_banner",
            "-nostats",
            *build_input_args(original_file),
            *build_input_args(re_encoded_file),
            "-filter_complex",
            build_quality_filter_complex(
                f"[0:{original_stream_index}]",
                f"[1:{re_encoded_stream_index}]",
                conversion_method.audio_filter,
            ),
            "-f",
            "null",
            "-",
        ]

        try:
            lines = ffmpeg_runner.stream_stderr(command)
            metrics = await parse_audio_quality_metrics(lines)
            if metrics.apsnr or metrics.asdr:
                quality_metrics[re_encoded_stream_index] = metrics
        except FFmpegProcessError as e:
            logger.error(
                f"Error calculating audio quality metrics for stream {re_encoded_stream_index}: {e}"
            )
            continue

    return quality_metrics


def check_audio_quality(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> dict[int, AudioQualityMetrics]:
    """Get audio quality metrics in a synchronous context."""
    return asyncio.run(get_audio_quality_metrics(converted_file, ffmpeg_runner))
