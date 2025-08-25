"""A module for checking the quality of audio streams."""

import asyncio
import re
from typing import AsyncIterable, NamedTuple, Optional

from logzero import logger

from .ffmpeg import FFmpegProcessError, execute_ffmpeg_stderr_streamed
from .video_file import ConvertedVideoFile


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


async def get_audio_quality_metrics(
    converted_file: ConvertedVideoFile,
) -> dict[int, AudioQualityMetrics]:
    """Calculate audio quality metrics for all converted audio streams.

    Args:
    ----
        converted_file: The converted video file.

    Returns
    -------
        A dictionary mapping the output audio stream index to its quality metrics.
    """
    quality_metrics: dict[int, AudioQualityMetrics] = {}

    for stream, stream_source in converted_file.stream_with_sources:
        if not (
            stream.codec_type == "audio"
            and stream_source.conversion_type == "converted"
        ):
            continue

        original_file = stream_source.source_video_path
        re_encoded_file = converted_file.path
        original_stream_index = stream_source.source_stream.index
        re_encoded_stream_index = stream.index

        command = [
            "-hide_banner",
            "-nostats",
            "-i",
            str(original_file),
            "-i",
            str(re_encoded_file),
            "-filter_complex",
            f"[0:{original_stream_index}][1:{re_encoded_stream_index}]apsnr;"
            + f"[0:{original_stream_index}][1:{re_encoded_stream_index}]asdr",
            "-f",
            "null",
            "-",
        ]

        try:
            lines = execute_ffmpeg_stderr_streamed(command)
            metrics = await parse_audio_quality_metrics(lines)
            if metrics.apsnr is not None or metrics.asdr is not None:
                quality_metrics[re_encoded_stream_index] = metrics
        except FFmpegProcessError as e:
            logger.exception(
                f"Error calculating audio quality metrics for stream {re_encoded_stream_index}: {e}"
            )
            continue

    return quality_metrics


def check_audio_quality(
    converted_file: ConvertedVideoFile,
) -> dict[int, AudioQualityMetrics]:
    """Get audio quality metrics in a synchronous context."""
    return asyncio.run(get_audio_quality_metrics(converted_file))
