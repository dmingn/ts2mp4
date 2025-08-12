"""A module for the VideoFile class."""

from enum import Enum, auto

from pydantic import BaseModel, ConfigDict, FilePath

from .media_info import MediaInfo, Stream, get_media_info


class VideoFile(BaseModel):
    """A class representing a video file."""

    path: FilePath

    model_config = ConfigDict(frozen=True)

    @property
    def media_info(self) -> MediaInfo:
        """Return media information for the file."""
        return get_media_info(self.path)

    @property
    def audio_streams(self) -> list[Stream]:
        """Return a list of audio streams."""
        return [
            stream for stream in self.media_info.streams if stream.codec_type == "audio"
        ]

    @property
    def valid_audio_streams(self) -> list[Stream]:
        """Return a list of valid audio streams (channels > 0)."""
        return [
            stream
            for stream in self.audio_streams
            if stream.channels is not None and stream.channels > 0
        ]

    def get_stream_by_index(self, stream_index: int) -> Stream:
        """Return the stream for a given stream index."""
        for stream in self.media_info.streams:
            if stream.index == stream_index:
                return stream
        raise ValueError(f"Stream {stream_index} not found in this video file")


class ConversionType(Enum):
    """An enumeration for stream conversion types."""

    CONVERTED = auto()
    COPIED = auto()
    RE_ENCODED = auto()


class StreamSource(BaseModel):
    """A class representing the source of a stream."""

    source_video_file: VideoFile
    source_stream_index: int
    conversion_type: ConversionType

    model_config = ConfigDict(frozen=True)


class ConvertedVideoFile(VideoFile):
    """A class representing a converted video file."""

    stream_sources: dict[int, StreamSource]

    def get_source_stream(self, stream: Stream) -> Stream:
        """Return the source stream for a given stream."""
        stream_source = self.stream_sources.get(stream.index)
        if not stream_source:
            raise ValueError(f"Stream {stream.index} not found in stream sources")
        return stream_source.source_video_file.get_stream_by_index(
            stream_source.source_stream_index
        )
