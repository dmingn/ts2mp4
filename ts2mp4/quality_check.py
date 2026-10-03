"""A module for checking the quality of audio streams."""

import asyncio
import re
from typing import AsyncIterable, NamedTuple, Optional

from logzero import logger

from .conversion_plan import EncodeAudio, FileConversionPlan
from .converted_video_file import ConvertedVideoFile
from .ffmpeg import FFmpegProcessError, FFmpegRunner


class AudioQualityMetrics(NamedTuple):
    """A class to hold audio quality metrics."""

    apsnr: Optional[float]  # Average Peak Signal-to-Noise Ratio
    asdr: Optional[float]  # Average Signal-to-Distortion Ratio


async def parse_audio_quality_metrics(
    output_lines: AsyncIterable[str],
) -> AudioQualityMetrics:
    """Parse FFmpeg output and log APSNR and ASDR metrics."""
    apsnr: Optional[float] = None
    asdr: Optional[float] = None

    async for line in output_lines:
        if "Parsed_apsnr" in line and apsnr is None:
            match = re.search(
                r"PSNR ch\d+: ([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|inf|-inf|-?nan) dB",
                line,
            )
            if match:
                try:
                    value_str = match.group(1)
                    if value_str == "-nan":
                        value_str = "nan"
                    apsnr = float(value_str)
                except ValueError as e:
                    logger.warning(f"Could not parse APSNR from line: {line} - {e}")
            else:
                logger.warning(f"Could not find APSNR in line: {line}")

        if "Parsed_asdr" in line and asdr is None:
            match = re.search(
                r"SDR ch\d+: ([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|inf|-inf|-?nan) dB",
                line,
            )
            if match:
                try:
                    value_str = match.group(1)
                    if value_str == "-nan":
                        value_str = "nan"
                    asdr = float(value_str)
                except ValueError as e:
                    logger.warning(f"Could not parse ASDR from line: {line} - {e}")
            else:
                logger.warning(f"Could not find ASDR in line: {line}")

    return AudioQualityMetrics(apsnr=apsnr, asdr=asdr)


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
            "-i",
            str(original_file),
            "-i",
            str(re_encoded_file),
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
            if metrics.apsnr is not None or metrics.asdr is not None:
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
