"""A module for checking the quality of audio streams."""

import asyncio
import math
import re
from pathlib import Path
from typing import AsyncIterable

from logzero import logger
from pydantic import BaseModel, ConfigDict

from .conversion_plan import EncodeAudio, FileConversionPlan
from .converted_video_file import ConvertedVideoFile
from .ffmpeg import FFmpegRunner
from .ffmpeg_input_args import build_input_args

# Re-encoding broadcast audio measured 22 dB or more, while misaligned, silent,
# or heavily degraded audio measured below 15 dB.
ASDR_THRESHOLD_DB = 15.0

_ASDR_LINE_PATTERN = re.compile(
    r"\[Parsed_asdr_\d+ @ [^\]]+\] SDR ch(?P<channel>\d+): "
    r"(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|-?inf|-?nan) dB"
)


async def parse_asdr(output_lines: AsyncIterable[str]) -> tuple[float, ...]:
    """Parse the Average Signal-to-Distortion Ratio of every channel from FFmpeg output."""
    asdr_by_channel: dict[int, float] = {}

    async for line in output_lines:
        match = _ASDR_LINE_PATTERN.search(line)
        if match is None:
            if "Parsed_asdr" in line:
                logger.warning(f"Could not parse ASDR from: {line}")
            continue

        asdr_by_channel[int(match["channel"])] = float(match["value"])

    return tuple(asdr_by_channel[channel] for channel in sorted(asdr_by_channel))


def _format_asdr(asdr: tuple[float, ...]) -> str:
    """Return a description of ``asdr``, such as ``ASDR=[30.00, 31.00]dB``."""
    return f"ASDR=[{', '.join(f'{value:.2f}' for value in asdr)}]dB"


def _meets_asdr_threshold(asdr: tuple[float, ...]) -> bool:
    """Return whether every channel's ASDR reaches ``ASDR_THRESHOLD_DB``.

    Channels silent in both streams have a NaN ASDR and are ignored. A stream
    without any channel does not meet the threshold.
    """
    return bool(asdr) and all(
        value >= ASDR_THRESHOLD_DB for value in asdr if not math.isnan(value)
    )


class AudioQualityReport(BaseModel):
    """The result of comparing re-encoded output streams against their sources."""

    asdr_by_output_index: dict[int, tuple[float, ...]]

    model_config = ConfigDict(frozen=True)

    @property
    def degraded_output_indices(self) -> frozenset[int]:
        """Return the indices of the output streams whose quality is too low."""
        return frozenset(
            output_index
            for output_index, asdr in self.asdr_by_output_index.items()
            if not _meets_asdr_threshold(asdr)
        )

    @property
    def is_ok(self) -> bool:
        """Return True if every re-encoded stream is close enough to its source."""
        return not self.degraded_output_indices


def build_reference_args(
    original_file: Path, stream_index: int, audio_filter: str | None
) -> list[str]:
    """Build the arguments that write an original stream to stdout as PCM.

    ``audio_filter`` is applied so that the stream has the same channel layout
    as the re-encoded stream. Normalizing the layout here keeps it from changing
    in the comparison, where a change would misalign the two streams.
    """
    return [
        "-hide_banner",
        "-nostats",
        *build_input_args(original_file),
        "-map",
        f"0:{stream_index}",
        *(["-af", audio_filter] if audio_filter is not None else []),
        "-c:a",
        "pcm_f32le",
        "-f",
        "nut",
        "pipe:1",
    ]


def build_comparison_args(re_encoded_file: Path, stream_index: int) -> list[str]:
    """Build the arguments that compare the PCM from stdin with a re-encoded stream."""
    return [
        "-hide_banner",
        "-nostats",
        "-f",
        "nut",
        "-i",
        "pipe:0",
        *build_input_args(re_encoded_file),
        "-filter_complex",
        f"[0:0][1:{stream_index}]asdr",
        "-f",
        "null",
        "-",
    ]


async def get_asdr(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> dict[int, tuple[float, ...]]:
    """Calculate the per-channel ASDR of all re-encoded audio streams.

    Args:
    ----
        converted_file: The converted video file.
        ffmpeg_runner: The FFmpegRunner used to compare the audio streams.

    Returns
    -------
        A dictionary mapping the output audio stream index to its per-channel ASDR.

    Raises
    ------
        FFmpegProcessError: If FFmpeg fails to compare a stream.
    """
    asdr_by_output_index: dict[int, tuple[float, ...]] = {}

    for stream_with_conversion_plan in converted_file.streams_with_conversion_plans:
        conversion_plan = stream_with_conversion_plan.conversion_plan
        if not isinstance(conversion_plan.conversion_method, EncodeAudio):
            continue

        re_encoded_stream_index = stream_with_conversion_plan.stream.index

        lines = ffmpeg_runner.stream_stderr_piped(
            build_reference_args(
                conversion_plan.source_stream.file.path,
                conversion_plan.source_stream.index,
                conversion_plan.conversion_method.audio_filter,
            ),
            build_comparison_args(converted_file.path, re_encoded_stream_index),
        )
        asdr = await parse_asdr(lines)
        logger.info(
            f"Audio quality for stream {re_encoded_stream_index}: {_format_asdr(asdr)}"
        )
        asdr_by_output_index[re_encoded_stream_index] = asdr

    return asdr_by_output_index


def check_audio_quality(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> AudioQualityReport:
    """Compare every re-encoded audio stream against its source.

    Raises
    ------
        FFmpegProcessError: If FFmpeg fails to compare a stream.
    """
    return AudioQualityReport(
        asdr_by_output_index=asyncio.run(get_asdr(converted_file, ffmpeg_runner))
    )
