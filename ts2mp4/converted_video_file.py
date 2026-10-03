"""Converted video file model."""

from functools import cached_property
from typing import Generic, Self

from pydantic import BaseModel, ConfigDict, model_validator

from .conversion_plan import (
    ConversionMethod,
    FileConversionPlanT,
    StreamConversionPlan,
    StreamT,
    is_audio_stream_plan,
    is_other_stream_plan,
    is_video_stream_plan,
)
from .video_file import (
    AudioStream,
    OtherStream,
    Stream,
    VideoFile,
    VideoStream,
)


class StreamWithConversionPlan(BaseModel, Generic[StreamT]):
    """An output stream paired with the plan that made it."""

    stream: StreamT
    conversion_plan: StreamConversionPlan[StreamT, ConversionMethod]

    model_config = ConfigDict(frozen=True)


AnyStreamWithConversionPlan = (
    StreamWithConversionPlan[VideoStream]
    | StreamWithConversionPlan[AudioStream]
    | StreamWithConversionPlan[OtherStream]
)


def _pair(
    stream: Stream, plan: StreamConversionPlan[Stream, ConversionMethod]
) -> AnyStreamWithConversionPlan:
    """Pair ``stream`` with ``plan``, requiring the same kind of stream."""
    match stream:
        case VideoStream() if is_video_stream_plan(plan):
            return StreamWithConversionPlan(stream=stream, conversion_plan=plan)
        case AudioStream() if is_audio_stream_plan(plan):
            return StreamWithConversionPlan(stream=stream, conversion_plan=plan)
        case OtherStream() if is_other_stream_plan(plan):
            return StreamWithConversionPlan(stream=stream, conversion_plan=plan)
        case _:
            raise ValueError(
                f"Stream type mismatch for stream index {stream.index} "
                f"in {stream.file.path.name}."
            )


class ConvertedVideoFile(VideoFile, Generic[FileConversionPlanT]):
    """A video file written from ``file_conversion_plan``."""

    file_conversion_plan: FileConversionPlanT

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_streams_match_plan(self) -> Self:
        """Reject output streams that do not pair with ``file_conversion_plan``."""
        self.streams_with_conversion_plans
        return self

    @cached_property
    def streams_with_conversion_plans(
        self,
    ) -> tuple[AnyStreamWithConversionPlan, ...]:
        """Return each output stream paired with its plan, in output index order."""
        streams = sorted(self.streams, key=lambda stream: stream.index)
        if len(streams) != len(self.file_conversion_plan):
            raise ValueError(
                f"Mismatch in stream counts for {self.path.name}: "
                f"{len(self.file_conversion_plan)} plans, "
                f"{len(streams)} output streams."
            )

        return tuple(
            _pair(stream, plan)
            for stream, plan in zip(streams, self.file_conversion_plan)
        )
