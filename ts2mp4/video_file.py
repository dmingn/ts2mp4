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

    @staticmethod
    def _is_valid_audio_stream(stream: Stream) -> bool:
        """Return True if the audio stream is valid."""
        return stream.channels is not None and stream.channels > 0

    @staticmethod
    def _is_valid_video_stream(stream: Stream) -> bool:
        """Return True if the video stream is valid."""
        return True

    @property
    def valid_audio_streams(self) -> tuple[Stream, ...]:
        """Return a tuple of valid audio streams."""
        return tuple(
            stream
            for stream in self.media_info.streams
            if stream.codec_type == "audio" and VideoFile._is_valid_audio_stream(stream)
        )

    @property
    def valid_video_streams(self) -> tuple[Stream, ...]:
        """Return a tuple of valid video streams."""
        return tuple(
            stream
            for stream in self.media_info.streams
            if stream.codec_type == "video" and VideoFile._is_valid_video_stream(stream)
        )

    @property
    def valid_streams(self) -> tuple[Stream, ...]:
        """Return a tuple of valid streams."""
        return self.valid_video_streams + self.valid_audio_streams


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
