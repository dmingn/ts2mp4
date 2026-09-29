"""Converted video file model."""

from collections.abc import Iterable
from typing import Generic, Iterator, Self, assert_never

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


def streams_by_unique_index(streams: Iterable[Stream]) -> dict[int, Stream]:
    """Map ``stream.index`` to stream, rejecting duplicate indices."""
    streams_by_index: dict[int, Stream] = {}
    for stream in streams:
        if stream.index in streams_by_index:
            raise ValueError(f"Duplicate stream index {stream.index}")
        streams_by_index[stream.index] = stream
    return streams_by_index


class ConvertedVideoFile(VideoFile, Generic[FileConversionPlanT]):
    """A class representing a converted video file.

    This class extends VideoFile to include information about how each stream
    in the converted file was created. ``file_conversion_plan`` contains
    ``StreamConversionPlan`` objects, where the position of each corresponds to
    the stream's index in the converted video file. Each ``StreamConversionPlan``
    object describes which original stream was used to generate that stream
    in the converted file, and how it was created (copied or encoded).
    """

    file_conversion_plan: FileConversionPlanT

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_file_conversion_plan(self) -> Self:
        """Require one plan per output stream, paired by matching index."""
        if len(self.file_conversion_plan) != len(self.streams):
            raise ValueError(
                f"Mismatch in stream counts for {self.path.name}: "
                f"{len(self.file_conversion_plan)} plans, "
                f"{len(self.streams)} output streams."
            )

        try:
            streams_by_index = streams_by_unique_index(self.streams)
        except ValueError as e:
            raise ValueError(f"Invalid streams for {self.path.name}: {e}") from e

        expected_indices = set(range(len(self.file_conversion_plan)))
        actual_indices = set(streams_by_index)
        if actual_indices != expected_indices:
            raise ValueError(
                f"Output stream indices {sorted(actual_indices)} do not match "
                f"file_conversion_plan positions {sorted(expected_indices)} "
                f"for {self.path.name}."
            )
        return self

    @property
    def streams_with_conversion_plans(
        self,
    ) -> Iterator[
        StreamWithConversionPlan[VideoStream]
        | StreamWithConversionPlan[AudioStream]
        | StreamWithConversionPlan[OtherStream]
    ]:
        """Return pairs of output streams and their conversion plans.

        Each ``file_conversion_plan`` position ``i`` is paired with the output stream
        whose ``index`` is ``i``.
        """
        streams_by_index = streams_by_unique_index(self.streams)
        for index, plan in enumerate(self.file_conversion_plan):
            try:
                stream = streams_by_index[index]
            except KeyError as e:
                raise RuntimeError(
                    f"No output stream with index {index} for {self.path.name}; "
                    f"file_conversion_plan position {index} requires a matching output index."
                ) from e
            match stream:
                case VideoStream():
                    if not is_video_stream_plan(plan):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithConversionPlan(stream=stream, conversion_plan=plan)
                case AudioStream():
                    if not is_audio_stream_plan(plan):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithConversionPlan(stream=stream, conversion_plan=plan)
                case OtherStream():
                    if not is_other_stream_plan(plan):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithConversionPlan(stream=stream, conversion_plan=plan)
                case _:
                    assert_never(stream)
