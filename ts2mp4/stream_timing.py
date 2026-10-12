"""A module for detecting re-encoded output streams shifted in time."""

import asyncio
from typing import assert_never

from logzero import logger
from pydantic import BaseModel, ConfigDict

from .conversion_plan import (
    Copy,
    EncodeAudioWithLibfdkAac,
    EncodeAudioWithNativeAac,
    EncodeVideo,
    FileConversionPlan,
)
from .converted_video_file import AnyStreamWithConversionPlan, ConvertedVideoFile
from .ffmpeg import FFmpegRunner
from .ffmpeg_input_args import build_zero_based_input_args
from .hashing import parse_framemd5
from .video_file import AudioStream

# With ``-fps_mode cfr``, FFmpeg fills the gap before the first video frame
# with copies of it, so only the end time can be compared. Re-encoded video
# ended 8 to 54 ms after its source in the recordings checked, and 179 ms
# before it when the video was shifted 230 ms early.
CFR_VIDEO_END_TOLERANCE_SECONDS = 0.1


class TimingReport(BaseModel):
    """The result of comparing re-encoded output streams against their sources."""

    shifted_output_indices: frozenset[int]

    model_config = ConfigDict(frozen=True)

    @property
    def is_ok(self) -> bool:
        """Return True if no re-encoded stream is shifted from its source."""
        return not self.shifted_output_indices


def _is_shifted_by_more_than(
    label: str,
    output_offset: float | None,
    source_offset: float | None,
    tolerance: float,
) -> bool:
    """Return True if ``output_offset`` differs from ``source_offset`` beyond ``tolerance``.

    Offsets that are unknown are not judged.
    """
    if output_offset is None or source_offset is None:
        logger.warning(
            f"Skipping timing check of {label}: "
            f"output {output_offset}, source {source_offset}"
        )
        return False

    if abs(output_offset - source_offset) > tolerance:
        logger.warning(
            f"{label} is shifted: "
            f"output {output_offset:.3f}s, source {source_offset:.3f}s"
        )
        return True

    return False


def _first_decoded_pts_args(stream: AudioStream) -> list[str]:
    """Return the ffmpeg arguments that decode the first sample of ``stream``."""
    return [
        "-hide_banner",
        "-nostats",
        "-copyts",
        *build_zero_based_input_args(stream.file.path, stream.file.start_time),
        "-map",
        f"0:{stream.index}",
        "-fps_mode",
        "passthrough",
        "-frames:a",
        "1",
        "-f",
        "framemd5",
        "-",
    ]


async def _read_first_decoded_pts(
    stream: AudioStream, ffmpeg_runner: FFmpegRunner
) -> float | None:
    output = b"".join(
        [
            chunk
            async for chunk in ffmpeg_runner.stream_stdout(
                _first_decoded_pts_args(stream)
            )
        ]
    )
    lines = output.decode("utf-8").splitlines()
    if not any(line.startswith("#tb 0: ") for line in lines):
        return None

    frames = parse_framemd5(lines)
    if not frames:
        return None

    return frames[0].pts


def first_decoded_pts(stream: AudioStream, ffmpeg_runner: FFmpegRunner) -> float | None:
    """Return the timestamp of the first sample ``stream`` decodes.

    The timestamp is in seconds from the start of the file. A packet that fails
    to decode produces no sample, so the timestamp is that of the next packet
    that does. The result is None when the stream has no decodable sample.

    Raises
    ------
        FFmpegProcessError: If ffmpeg fails to read the stream.
    """
    return asyncio.run(_read_first_decoded_pts(stream, ffmpeg_runner))


def _is_shifted(
    stream_with_conversion_plan: AnyStreamWithConversionPlan,
    ffmpeg_runner: FFmpegRunner,
) -> bool:
    """Return True if a re-encoded output stream is shifted from its source."""
    stream = stream_with_conversion_plan.stream
    source_stream = stream_with_conversion_plan.conversion_plan.source_stream
    conversion_method = stream_with_conversion_plan.conversion_plan.conversion_method

    match conversion_method:
        case Copy():
            return False
        case EncodeVideo(fps_mode="cfr"):
            return _is_shifted_by_more_than(
                f"End offset of output stream at index {stream.index}",
                stream.end_offset,
                source_stream.end_offset,
                CFR_VIDEO_END_TOLERANCE_SECONDS,
            )
        case EncodeVideo(fps_mode=fps_mode):
            raise NotImplementedError(
                f"Timing check for video encoded with fps_mode {fps_mode} "
                "is not implemented."
            )
        case EncodeAudioWithLibfdkAac() | EncodeAudioWithNativeAac():
            if not isinstance(stream, AudioStream) or not isinstance(
                source_stream, AudioStream
            ):
                raise ValueError(
                    f"Stream type mismatch for stream index {stream.index} "
                    f"in {stream.file.path.name}."
                )

            output_pts = first_decoded_pts(stream, ffmpeg_runner)
            source_pts = first_decoded_pts(source_stream, ffmpeg_runner)
            if output_pts is None or source_pts is None:
                raise RuntimeError(
                    "Could not read the first decoded sample of output stream "
                    f"at index {stream.index} in {stream.file.path.name}: "
                    f"output {output_pts}, source {source_pts}"
                )

            # Decoding reports the timestamp stored in the container. That
            # timestamp is in the stream's time base, so the two may differ by
            # the coarser time base.
            return _is_shifted_by_more_than(
                f"Start offset of output stream at index {stream.index}",
                output_pts,
                source_pts,
                float(max(stream.time_base, source_stream.time_base)),
            )
        case _ as unreachable:
            assert_never(unreachable)


def check_timing(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> TimingReport:
    """Compare the timing of every re-encoded stream in a file against its source.

    Re-encoded audio is compared by the first sample each stream decodes.
    Copied streams are compared frame by frame by the integrity check instead.

    Raises
    ------
        RuntimeError: If a re-encoded audio stream has no decodable sample.
    """
    return TimingReport(
        shifted_output_indices=frozenset(
            stream_with_conversion_plan.stream.index
            for stream_with_conversion_plan in converted_file.streams_with_conversion_plans
            if _is_shifted(stream_with_conversion_plan, ffmpeg_runner)
        )
    )
