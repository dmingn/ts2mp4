"""Stream source and converted video file models."""

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


VideoConversion = Copy | EncodeVideo
AudioConversion = Copy | EncodeAudio
Conversion = VideoConversion | AudioConversion
ConversionT = TypeVar("ConversionT", bound=Conversion, covariant=True)


class StreamSource(BaseModel, Generic[StreamT, ConversionT]):
    """A class representing the source of a stream."""

    source_stream: StreamT
    conversion: ConversionT

    model_config = ConfigDict(frozen=True)


class StreamWithSource(BaseModel, Generic[StreamT]):
    """A class representing a stream with its source."""

    stream: StreamT
    source: StreamSource[StreamT, Conversion]

    model_config = ConfigDict(frozen=True)


def is_video_stream_source(
    source: StreamSource[Stream, ConversionT],
) -> TypeGuard[StreamSource[VideoStream, ConversionT]]:
    """Return True if the source is a video stream source."""
    return isinstance(source.source_stream, VideoStream)


def is_audio_stream_source(
    source: StreamSource[Stream, ConversionT],
) -> TypeGuard[StreamSource[AudioStream, ConversionT]]:
    """Return True if the source is an audio stream source."""
    return isinstance(source.source_stream, AudioStream)


def is_other_stream_source(
    source: StreamSource[Stream, ConversionT],
) -> TypeGuard[StreamSource[OtherStream, ConversionT]]:
    """Return True if the source is an other stream source."""
    return isinstance(source.source_stream, OtherStream)


class StreamSources(RootModel[tuple[StreamSource[Stream, Conversion], ...]]):
    """A tuple of StreamSource objects."""

    model_config = ConfigDict(frozen=True)

    def __iter__(self) -> Iterator[StreamSource[Stream, Conversion]]:  # type: ignore[override]
        """Return an iterator over the StreamSource objects."""
        return iter(self.root)

    def __getitem__(self, item: int) -> StreamSource[Stream, Conversion]:
        """Return the StreamSource object at the given index."""
        return self.root[item]

    def __len__(self) -> int:
        """Return the number of StreamSource objects."""
        return len(self.root)

    @property
    def video_stream_sources(
        self,
    ) -> frozenset[StreamSource[VideoStream, Conversion]]:
        """Return a set of video stream sources."""
        return frozenset(filter(is_video_stream_source, self.root))

    @property
    def audio_stream_sources(
        self,
    ) -> frozenset[StreamSource[AudioStream, Conversion]]:
        """Return a set of audio stream sources."""
        return frozenset(filter(is_audio_stream_source, self.root))

    @property
    def source_video_files(self) -> frozenset[VideoFile]:
        """Return a set of source video files for the stream sources."""
        return frozenset(stream.source_stream.file for stream in self.root)

    @property
    def default_stream_indices(self) -> frozenset[int]:
        """Return the output stream indices to mark with disposition default."""
        return get_default_stream_indices(
            [source.source_stream for source in self.root]
        )


StreamSourcesT = TypeVar("StreamSourcesT", bound=StreamSources, covariant=True)


def streams_by_unique_index(streams: Iterable[Stream]) -> dict[int, Stream]:
    """Map ``stream.index`` to stream, rejecting duplicate indices."""
    streams_by_index: dict[int, Stream] = {}
    for stream in streams:
        if stream.index in streams_by_index:
            raise ValueError(f"Duplicate stream index {stream.index}")
        streams_by_index[stream.index] = stream
    return streams_by_index


class ConvertedVideoFile(VideoFile, Generic[StreamSourcesT]):
    """A class representing a converted video file.

    This class extends VideoFile to include information about how each stream
    in the converted file was created. The ``stream_sources`` tuple contains
    ``StreamSource`` objects, where the position in the tuple corresponds to
    the stream's index in the converted video file. Each ``StreamSource``
    object describes which original stream was used to generate that stream
    in the converted file, and how it was created (copied or encoded).
    """

    stream_sources: StreamSourcesT

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_stream_sources(self) -> Self:
        """Require one source per output stream, paired by matching index."""
        if len(self.stream_sources) != len(self.streams):
            raise ValueError(
                f"Mismatch in stream counts for {self.path.name}: "
                f"{len(self.stream_sources)} sources, "
                f"{len(self.streams)} output streams."
            )

        try:
            streams_by_index = streams_by_unique_index(self.streams)
        except ValueError as e:
            raise ValueError(f"Invalid streams for {self.path.name}: {e}") from e

        expected_indices = set(range(len(self.stream_sources)))
        actual_indices = set(streams_by_index)
        if actual_indices != expected_indices:
            raise ValueError(
                f"Output stream indices {sorted(actual_indices)} do not match "
                f"stream_sources positions {sorted(expected_indices)} "
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

        Each ``stream_sources`` position ``i`` is paired with the output stream
        whose ``index`` is ``i``.
        """
        streams_by_index = streams_by_unique_index(self.streams)
        for index, source in enumerate(self.stream_sources):
            try:
                stream = streams_by_index[index]
            except KeyError as e:
                raise RuntimeError(
                    f"No output stream with index {index} for {self.path.name}; "
                    f"stream_sources position {index} requires a matching output index."
                ) from e
            match stream:
                case VideoStream():
                    if not is_video_stream_source(source):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithSource(stream=stream, source=source)
                case AudioStream():
                    if not is_audio_stream_source(source):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithSource(stream=stream, source=source)
                case OtherStream():
                    if not is_other_stream_source(source):
                        raise RuntimeError(
                            f"Stream type mismatch for stream index {stream.index}"
                        )
                    yield StreamWithSource(stream=stream, source=source)
                case _:
                    assert_never(stream)
