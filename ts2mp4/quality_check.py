import re
from pathlib import Path
from typing import NamedTuple, Optional

from logzero import logger

from .ffmpeg import execute_ffmpeg


class AudioQualityMetrics(NamedTuple):
    apsnr: Optional[float]  # Average Peak Signal-to-Noise Ratio
    asdr: Optional[float]  # Average Signal-to-Distortion Ratio


def parse_audio_quality_metrics(output: str) -> AudioQualityMetrics:
    """Parses FFmpeg output and logs APSNR and ASDR metrics."""
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
    original_file: Path,
    re_encoded_file: Path,
    audio_stream_index: int,
) -> Optional[AudioQualityMetrics]:
    """Calculates APSNR and ASDR for an audio stream using FFmpeg.

    Args:
    ----
        original_file: Path to the original file.
        re_encoded_file: Path to the re-encoded file.
        audio_stream_index: The index of the audio stream to analyze.

    Returns:
    -------
        An AudioQualityMetrics namedtuple containing apsnr and asdr, or None if metrics could not be calculated.
    """
    command = [
        "-i",
        str(original_file),
        "-i",
        str(re_encoded_file),
        "-filter_complex",
        f"[0:a:{audio_stream_index}][1:a:{audio_stream_index}]apsnr;"
        + f"[0:a:{audio_stream_index}][1:a:{audio_stream_index}]asdr",
        "-f",
        "null",
        "-",
    ]

    result = execute_ffmpeg(command)
    if result.returncode != 0:
        logger.error(f"Error calculating audio quality metrics: {result.stderr}")
        return None

    return parse_audio_quality_metrics(result.stderr)
