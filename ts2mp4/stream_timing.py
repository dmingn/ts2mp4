"""A module for detecting re-encoded output streams shifted in time."""

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


def _is_shifted(stream_with_conversion_plan: AnyStreamWithConversionPlan) -> bool:
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
            # The output records its start time in units of its time base, so
            # it may differ from the source by up to the coarser time base.
            return _is_shifted_by_more_than(
                f"Start offset of output stream at index {stream.index}",
                stream.start_offset,
                source_stream.start_offset,
                float(max(stream.time_base, source_stream.time_base)),
            )
        case _ as unreachable:
            assert_never(unreachable)


def check_timing(
    converted_file: ConvertedVideoFile[FileConversionPlan],
) -> TimingReport:
    """Compare the timing of every re-encoded stream in a file against its source.

    Copied streams are compared frame by frame by the integrity check instead.
    """
    return TimingReport(
        shifted_output_indices=frozenset(
            stream_with_conversion_plan.stream.index
            for stream_with_conversion_plan in converted_file.streams_with_conversion_plans
            if _is_shifted(stream_with_conversion_plan)
        )
    )
