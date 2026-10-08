"""VideoFile and domain stream models."""

from __future__ import annotations

from fractions import Fraction

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
    def start_time(self) -> float | None:
        """Return the container start time in seconds, if known."""
        if self.probe.format is None:
            return None
        return self.probe.format.start_time

    @property
    def duration(self) -> float | None:
        """Return the container duration in seconds, if known."""
        if self.probe.format is None:
            return None
        return self.probe.format.duration

    @property
    def is_matroska(self) -> bool:
        """Return True if the container is Matroska."""
        if self.probe.format is None or self.probe.format.format_name is None:
            return False
        return "matroska" in self.probe.format.format_name.split(",")

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
    """A stream slot in a VideoFile, identified by index.

    Codec metadata is derived from ``file.probe`` at ``index``.
    """

    model_config = ConfigDict(frozen=True)

    file: VideoFile
    index: int

    def __lt__(self, other: object) -> bool:
        """Order by ``file.path``, then ``index``."""
        if not isinstance(other, BaseStream):
            return NotImplemented
        return (self.file.path, self.index) < (other.file.path, other.index)

    @property
    def _ffprobe_stream(self) -> FFprobeStream:
        for stream in self.file.probe.streams:
            if stream.index == self.index:
                return stream
        raise ValueError(f"Stream index {self.index} not found in {self.file.path}")

    @property
    def time_base(self) -> Fraction:
        """Return the unit of the stream timestamps in seconds."""
        return self._ffprobe_stream.time_base

    @property
    def start_offset(self) -> float | None:
        """Return the offset of the stream start from the file start in seconds, if known."""
        stream_start_time = self._ffprobe_stream.start_time
        file_start_time = self.file.start_time
        if stream_start_time is None or file_start_time is None:
            return None
        return stream_start_time - file_start_time

    @property
    def end_offset(self) -> float | None:
        """Return the offset of the stream end from the file start in seconds, if known."""
        start_offset = self.start_offset
        duration = self.duration
        if start_offset is None or duration is None:
            return None
        return start_offset + duration

    @property
    def duration(self) -> float | None:
        """Return the stream duration in seconds, if known.

        Matroska records only the end time of each stream, in its ``DURATION``
        tag, so the duration is that end time minus the stream start time.
        """
        ffprobe_stream = self._ffprobe_stream
        if not self.file.is_matroska:
            return ffprobe_stream.duration

        end_time = ffprobe_stream.tags.duration
        start_time = ffprobe_stream.start_time
        if end_time is None or start_time is None:
            return None

        return end_time - start_time

    @property
    def codec_type(self) -> str:
        """Return the ffprobe codec_type."""
        return self._ffprobe_stream.codec_type


class VideoStream(BaseStream):
    """A video stream belonging to a VideoFile."""

    @property
    def width(self) -> int | None:
        """Return the frame width in pixels, if known."""
        return self._ffprobe_stream.width

    @property
    def height(self) -> int | None:
        """Return the frame height in pixels, if known."""
        return self._ffprobe_stream.height


class AudioStream(BaseStream):
    """An audio stream belonging to a VideoFile."""

    @property
    def codec_name(self) -> str | None:
        """Return the audio codec name, if known."""
        return self._ffprobe_stream.codec_name

    @property
    def profile(self) -> str | None:
        """Return the audio codec profile, if known."""
        return self._ffprobe_stream.profile

    @property
    def bit_rate(self) -> int | None:
        """Return the audio bit rate, if known."""
        return self._ffprobe_stream.bit_rate

    @property
    def channels(self) -> int | None:
        """Return the channel count, if known."""
        return self._ffprobe_stream.channels

    @property
    def sample_rate(self) -> int | None:
        """Return the sample rate in Hz, if known."""
        return self._ffprobe_stream.sample_rate


class OtherStream(BaseStream):
    """A non-video, non-audio stream belonging to a VideoFile."""


Stream = VideoStream | AudioStream | OtherStream


def _to_domain_stream(file: VideoFile, probe: FFprobeStream) -> Stream:
    """Map an ffprobe stream entry to a domain stream bound to ``file``."""
    match probe.codec_type:
        case "video":
            return VideoStream(file=file, index=probe.index)
        case "audio":
            return AudioStream(file=file, index=probe.index)
        case _:
            return OtherStream(file=file, index=probe.index)


VideoFile.model_rebuild()
BaseStream.model_rebuild()
VideoStream.model_rebuild()
AudioStream.model_rebuild()
OtherStream.model_rebuild()
