"""A module for checking the quality of audio streams."""

import re
from typing import NamedTuple, Optional

from logzero import logger

from .ffmpeg import execute_ffmpeg
from .video_file import ConversionType, ConvertedVideoFile


class AudioQualityMetrics(NamedTuple):
    """A class to hold audio quality metrics."""

    apsnr: Optional[float]  # Average Peak Signal-to-Noise Ratio
    asdr: Optional[float]  # Average Signal-to-Distortion Ratio


def parse_audio_quality_metrics(output: str) -> AudioQualityMetrics:
    """Parse FFmpeg output and log APSNR and ASDR metrics."""
    apsnr = None
    asdr = None

    for line in output.splitlines():
        if "Parsed_apsnr" in line:
            match = re.search(
                r"PSNR ch0: ([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|inf|-inf|nan) dB",
                line,
            )
            if match:
                try:
                    apsnr = float(match.group(1))
                except ValueError as e:
                    logger.warning(f"Could not parse APSNR from line: {line} - {e}")
            else:
                logger.warning(f"Could not find APSNR in line: {line}")

        if "Parsed_asdr" in line:
            match = re.search(
                r"SDR ch0: ([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|inf|-inf|nan) dB",
                line,
            )
            if match:
                try:
                    asdr = float(match.group(1))
                except ValueError as e:
                    logger.warning(f"Could not parse ASDR from line: {line} - {e}")
            else:
                logger.warning(f"Could not find ASDR in line: {line}")

    return AudioQualityMetrics(apsnr=apsnr, asdr=asdr)


def get_audio_quality_metrics(
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
        if (
            stream.codec_type != "audio"
            or stream_source.conversion_type != ConversionType.CONVERTED
        ):
            continue

        original_file = stream_source.source_video_file.path
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

        result = execute_ffmpeg(command)
        if result.returncode != 0:
            logger.error(
                f"Error calculating audio quality metrics for stream {re_encoded_stream_index}: {result.stderr}"
            )
            continue

        metrics = parse_audio_quality_metrics(result.stderr)
        if metrics.apsnr is not None or metrics.asdr is not None:
            quality_metrics[re_encoded_stream_index] = metrics

    return quality_metrics
