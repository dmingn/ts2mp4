"""A module for the VideoFile class."""

from typing import Generic, Iterator, Literal, TypeGuard, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    FilePath,
    RootModel,
    model_validator,
)

from .media_info import AudioStream, MediaInfo, Stream, VideoStream, get_media_info

StreamT = TypeVar("StreamT", bound=Stream, covariant=True)


class VideoFile(BaseModel):
    """A class representing a video file."""

    path: FilePath

    model_config = ConfigDict(frozen=True)

    @property
    def media_info(self) -> MediaInfo:
        """Return media information for the file."""
        return get_media_info(self.path)

    @staticmethod
    def _is_valid_audio_stream(stream: AudioStream) -> bool:
        """Return True if the audio stream is valid."""
        return stream.channels is not None and stream.channels > 0

    @staticmethod
    def _is_valid_video_stream(stream: VideoStream) -> bool:
        """Return True if the video stream is valid."""
        return True

    @property
    def valid_audio_streams(self) -> tuple[AudioStream, ...]:
        """Return a tuple of valid audio streams."""
        return tuple(
            stream
            for stream in self.media_info.streams
            if isinstance(stream, AudioStream)
            and VideoFile._is_valid_audio_stream(stream)
        )

    @property
    def valid_video_streams(self) -> tuple[VideoStream, ...]:
        """Return a tuple of valid video streams."""
        return tuple(
            stream
            for stream in self.media_info.streams
            if isinstance(stream, VideoStream)
            and VideoFile._is_valid_video_stream(stream)
        )

    @property
    def valid_streams(self) -> tuple[Stream, ...]:
        """Return a tuple of valid streams."""
        return self.valid_video_streams + self.valid_audio_streams


ConversionType = Literal["converted", "copied"]
ConversionTypeT = TypeVar("ConversionTypeT", bound=ConversionType, covariant=True)


class StreamSource(BaseModel, Generic[StreamT, ConversionTypeT]):
    """A class representing the source of a stream."""

    source_video_path: FilePath
    source_stream: StreamT
    conversion_type: ConversionTypeT

    model_config = ConfigDict(frozen=True)


def is_video_stream_source(
    source: StreamSource[Stream, ConversionTypeT],
) -> TypeGuard[StreamSource[VideoStream, ConversionTypeT]]:
    """Return True if the source is a video stream source."""
    return isinstance(source.source_stream, VideoStream)


def is_audio_stream_source(
    source: StreamSource[Stream, ConversionTypeT],
) -> TypeGuard[StreamSource[AudioStream, ConversionTypeT]]:
    """Return True if the source is an audio stream source."""
    return isinstance(source.source_stream, AudioStream)


class StreamSources(RootModel[tuple[StreamSource[Stream, ConversionType], ...]]):
    """A tuple of StreamSource objects."""

    model_config = ConfigDict(frozen=True)

    def __iter__(self) -> Iterator[StreamSource[Stream, ConversionType]]:  # type: ignore[override]
        """Return an iterator over the StreamSource objects."""
        return iter(self.root)

    def __getitem__(self, item: int) -> StreamSource[Stream, ConversionType]:
        """Return the StreamSource object at the given index."""
        return self.root[item]

    def __len__(self) -> int:
        """Return the number of StreamSource objects."""
        return len(self.root)

    @property
    def video_stream_sources(
        self,
    ) -> frozenset[StreamSource[VideoStream, ConversionType]]:
        """Return a set of video stream sources."""
        return frozenset(filter(is_video_stream_source, self.root))

    @property
    def audio_stream_sources(
        self,
    ) -> frozenset[StreamSource[AudioStream, ConversionType]]:
        """Return a set of audio stream sources."""
        return frozenset(filter(is_audio_stream_source, self.root))

    @property
    def source_video_files(self) -> frozenset[VideoFile]:
        """Return a set of source video files for the stream sources."""
        return frozenset(
            VideoFile(path=stream.source_video_path) for stream in self.root
        )


class ConvertedVideoFile(VideoFile):
    """A class representing a converted video file.

    This class extends VideoFile to include information about how each stream
    in the converted file was created. The `stream_sources` tuple contains
    `StreamSource` objects, where the position in the tuple corresponds to
    the stream's index in the converted video file. Each `StreamSource` object
    describes which original stream (from which source file) was used to
    generate that stream in the converted file, and how it was created
    (copied or converted).
    """

    stream_sources: StreamSources

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_stream_counts(self) -> "ConvertedVideoFile":
        """Validate that the number of stream sources matches the number of streams."""
        if len(self.stream_sources) != len(self.media_info.streams):
            raise ValueError(
                f"Mismatch in stream counts for {self.path.name}: "
                f"{len(self.stream_sources)} sources, "
                f"{len(self.media_info.streams)} output streams."
            )
        return self

    @property
    def stream_with_sources(
        self,
    ) -> Iterator[tuple[Stream, StreamSource[Stream, ConversionType]]]:
        """Return a zip object of output streams and their sources."""
        return zip(self.media_info.streams, self.stream_sources)
