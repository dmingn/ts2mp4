"""Conversion plan and converted video file models."""

from collections.abc import Iterable
from typing import Generic, Iterator, Self, TypeGuard, TypeVar, assert_never

from pydantic import BaseModel, ConfigDict, RootModel, model_validator

from .stream_disposition import get_default_stream_indices
from .video_file import (
    AudioStream,
    OtherStream,
    Stream,
    VideoFile,
    VideoStream,
)

StreamT = TypeVar("StreamT", bound=Stream, covariant=True)


class Copy(BaseModel):
    """Copy the source stream without re-encoding."""

    model_config = ConfigDict(frozen=True)


class EncodeVideo(BaseModel):
    """Re-encode the source video stream with the given encoder options."""

    codec: str
    crf: int
    preset: str
    video_filter: str | None = None
    fps_mode: str | None = None

    model_config = ConfigDict(frozen=True)


class EncodeAudio(BaseModel):
    """Re-encode the source audio stream with the given encoder options."""

    codec: str
    sample_rate: int | None = None
    channels: int | None = None
    profile: str | None = None
    bit_rate: int | None = None

    model_config = ConfigDict(frozen=True)


VideoConversionMethod = Copy | EncodeVideo
AudioConversionMethod = Copy | EncodeAudio
ConversionMethod = VideoConversionMethod | AudioConversionMethod
ConversionMethodT = TypeVar("ConversionMethodT", bound=ConversionMethod, covariant=True)


class StreamConversionPlan(BaseModel, Generic[StreamT, ConversionMethodT]):
    """How one output stream is made from ``source_stream``."""

    source_stream: StreamT
    conversion_method: ConversionMethodT

    model_config = ConfigDict(frozen=True)


class StreamWithSource(BaseModel, Generic[StreamT]):
    """A class representing a stream with its source."""

    stream: StreamT
    source: StreamConversionPlan[StreamT, ConversionMethod]

    model_config = ConfigDict(frozen=True)


def is_video_stream_plan(
    plan: StreamConversionPlan[Stream, ConversionMethodT],
) -> TypeGuard[StreamConversionPlan[VideoStream, ConversionMethodT]]:
    """Return True if ``plan`` converts a video stream."""
    return isinstance(plan.source_stream, VideoStream)


def is_audio_stream_plan(
    plan: StreamConversionPlan[Stream, ConversionMethodT],
) -> TypeGuard[StreamConversionPlan[AudioStream, ConversionMethodT]]:
    """Return True if ``plan`` converts an audio stream."""
    return isinstance(plan.source_stream, AudioStream)


def is_other_stream_plan(
    plan: StreamConversionPlan[Stream, ConversionMethodT],
) -> TypeGuard[StreamConversionPlan[OtherStream, ConversionMethodT]]:
    """Return True if ``plan`` converts an other stream."""
    return isinstance(plan.source_stream, OtherStream)


class FileConversionPlan(
    RootModel[tuple[StreamConversionPlan[Stream, ConversionMethod], ...]]
):
    """A tuple of StreamConversionPlan objects."""

    model_config = ConfigDict(frozen=True)

    def __iter__(self) -> Iterator[StreamConversionPlan[Stream, ConversionMethod]]:  # type: ignore[override]
        """Return an iterator over the StreamConversionPlan objects."""
        return iter(self.root)

    def __getitem__(self, item: int) -> StreamConversionPlan[Stream, ConversionMethod]:
        """Return the StreamConversionPlan object at the given index."""
        return self.root[item]

    def __len__(self) -> int:
        """Return the number of StreamConversionPlan objects."""
        return len(self.root)

    @property
    def video_stream_plans(
        self,
    ) -> frozenset[StreamConversionPlan[VideoStream, ConversionMethod]]:
        """Return the plans that convert video streams."""
        return frozenset(filter(is_video_stream_plan, self.root))

    @property
    def audio_stream_plans(
        self,
    ) -> frozenset[StreamConversionPlan[AudioStream, ConversionMethod]]:
        """Return the plans that convert audio streams."""
        return frozenset(filter(is_audio_stream_plan, self.root))

    @property
    def source_video_files(self) -> frozenset[VideoFile]:
        """Return a set of source video files for the plan."""
        return frozenset(plan.source_stream.file for plan in self.root)

    @property
    def default_stream_indices(self) -> frozenset[int]:
        """Return the output stream indices to mark with disposition default."""
        return get_default_stream_indices([plan.source_stream for plan in self.root])


FileConversionPlanT = TypeVar(
    "FileConversionPlanT", bound=FileConversionPlan, covariant=True
)


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
    def stream_with_sources(
        self,
    ) -> Iterator[
        StreamWithSource[VideoStream]
        | StreamWithSource[AudioStream]
        | StreamWithSource[OtherStream]
    ]:
        """Return pairs of output streams and their sources.

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
                    yield StreamWithSource(stream=stream, source=plan)
                case AudioStream():
                    if not is_audio_stream_plan(plan):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithSource(stream=stream, source=plan)
                case OtherStream():
                    if not is_other_stream_plan(plan):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithSource(stream=stream, source=plan)
                case _:
                    assert_never(stream)
