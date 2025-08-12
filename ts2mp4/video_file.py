"""A module for the VideoFile class."""

from enum import Enum, auto

from pydantic import BaseModel, ConfigDict, FilePath, NonNegativeInt

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


class ConversionType(Enum):
    """An enumeration for stream conversion types."""

    CONVERTED = auto()
    COPIED = auto()


class StreamSource(BaseModel):
    """A class representing the source of a stream."""

    source_video_file: VideoFile
    source_stream_index: NonNegativeInt
    conversion_type: ConversionType

    model_config = ConfigDict(frozen=True)


StreamSources = tuple[StreamSource, ...]


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
