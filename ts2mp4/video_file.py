"""A module for the VideoFile class."""

from enum import Enum, auto
from typing import Mapping

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
    def video_streams(self) -> list[Stream]:
        """Return a list of video streams."""
        return [
            stream for stream in self.media_info.streams if stream.codec_type == "video"
        ]

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
    RE_ENCODED = auto()


class StreamSource(BaseModel):
    """A class representing the source of a stream."""

    source_video_file: "VideoFile"
    source_stream_index: int
    conversion_type: ConversionType

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class ConvertedVideoFile(VideoFile):
    """A class representing a converted video file."""

    stream_sources: Mapping[int, StreamSource]
