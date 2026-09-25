"""VideoFile and domain stream models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, FilePath

from .ffprobe_schema import FFprobeOutput, FFprobeStream, probe_file


class VideoFile(BaseModel):
    """A class representing a video file."""

    path: FilePath

    model_config = ConfigDict(frozen=True)

    @property
    def probe(self) -> FFprobeOutput:
        """Return the ffprobe output for this file."""
        return probe_file(self.path)

    @property
    def streams(self) -> frozenset[Stream]:
        """Return domain streams belonging to this file."""
        return frozenset(
            _to_domain_stream(self, stream) for stream in self.probe.streams
        )

    @property
    def duration(self) -> float | None:
        """Return the container duration in seconds, if known."""
        if self.probe.format is None:
            return None
        return self.probe.format.duration

    @staticmethod
    def _is_valid_audio_stream(stream: AudioStream) -> bool:
        """Return True if the audio stream is valid."""
        return stream.channels is not None and stream.channels > 0

    @staticmethod
    def _is_valid_video_stream(stream: VideoStream) -> bool:
        """Return True if the video stream is valid."""
        return True

    @property
    def valid_audio_streams(self) -> frozenset[AudioStream]:
        """Return valid audio streams."""
        return frozenset(
            stream
            for stream in self.streams
            if isinstance(stream, AudioStream)
            and VideoFile._is_valid_audio_stream(stream)
        )

    @property
    def valid_video_streams(self) -> frozenset[VideoStream]:
        """Return valid video streams."""
        return frozenset(
            stream
            for stream in self.streams
            if isinstance(stream, VideoStream)
            and VideoFile._is_valid_video_stream(stream)
        )

    @property
    def valid_streams(self) -> frozenset[VideoStream | AudioStream]:
        """Return valid video and audio streams."""
        return self.valid_video_streams | self.valid_audio_streams


class BaseStream(BaseModel):
    """A stream slot in a VideoFile, identified by index."""

    model_config = ConfigDict(frozen=True)

    file: VideoFile
    index: int
    duration: float | None = None

    def __lt__(self, other: object) -> bool:
        """Order by ``file.path``, then ``index``."""
        if not isinstance(other, BaseStream):
            return NotImplemented
        return (self.file.path, self.index) < (other.file.path, other.index)


class VideoStream(BaseStream):
    """A video stream belonging to a VideoFile."""

    codec_type: Literal["video"] = "video"
    width: int | None = None
    height: int | None = None


class AudioStream(BaseStream):
    """An audio stream belonging to a VideoFile."""

    codec_type: Literal["audio"] = "audio"
    codec_name: str | None = None
    profile: str | None = None
    bit_rate: int | None = None
    channels: int | None = None
    sample_rate: int | None = None


class OtherStream(BaseStream):
    """A non-video, non-audio stream belonging to a VideoFile."""

    codec_type: str


Stream = VideoStream | AudioStream | OtherStream


def _to_domain_stream(file: VideoFile, probe: FFprobeStream) -> Stream:
    """Map an ffprobe stream entry to a domain stream bound to ``file``."""
    match probe.codec_type:
        case "video":
            return VideoStream(
                file=file,
                index=probe.index,
                duration=probe.duration,
                width=probe.width,
                height=probe.height,
            )
        case "audio":
            return AudioStream(
                file=file,
                index=probe.index,
                duration=probe.duration,
                codec_name=probe.codec_name,
                profile=probe.profile,
                bit_rate=probe.bit_rate,
                channels=probe.channels,
                sample_rate=probe.sample_rate,
            )
        case _:
            return OtherStream(
                file=file,
                index=probe.index,
                duration=probe.duration,
                codec_type=probe.codec_type,
            )


VideoFile.model_rebuild()
BaseStream.model_rebuild()
VideoStream.model_rebuild()
AudioStream.model_rebuild()
OtherStream.model_rebuild()
