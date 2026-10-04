"""Conversion plan models describing how each output stream is made."""

from typing import Generic, Iterator, Literal, TypeGuard, TypeVar

from pydantic import BaseModel, ConfigDict, RootModel

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


class BitRate(BaseModel):
    """Encode at the given target bit rate."""

    bit_rate: int

    model_config = ConfigDict(frozen=True)


class LibfdkVbrMode(BaseModel):
    """Encode in the given VBR mode of libfdk_aac."""

    mode: int

    model_config = ConfigDict(frozen=True)


class EncodeAudio(BaseModel):
    """Re-encode the source audio stream with the given encoder options."""

    sample_rate: int | None = None
    channels: int | None = None
    profile: str | None = None
    audio_filter: str | None = None

    model_config = ConfigDict(frozen=True)


class EncodeAudioWithLibfdkAac(EncodeAudio):
    """Re-encode the source audio stream with libfdk_aac."""

    codec: Literal["libfdk_aac"] = "libfdk_aac"
    rate_control: BitRate | LibfdkVbrMode | None = None


class EncodeAudioWithNativeAac(EncodeAudio):
    """Re-encode the source audio stream with FFmpeg's native aac encoder."""

    codec: Literal["aac"] = "aac"
    rate_control: BitRate | None = None


VideoConversionMethod = Copy | EncodeVideo
AudioEncodingMethod = EncodeAudioWithLibfdkAac | EncodeAudioWithNativeAac
AudioConversionMethod = Copy | AudioEncodingMethod
ConversionMethod = VideoConversionMethod | AudioConversionMethod
ConversionMethodT = TypeVar("ConversionMethodT", bound=ConversionMethod, covariant=True)


class StreamConversionPlan(BaseModel, Generic[StreamT, ConversionMethodT]):
    """How one output stream is made from ``source_stream``."""

    source_stream: StreamT
    conversion_method: ConversionMethodT

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
    """The StreamConversionPlan for each output stream of one file.

    The plan at position ``i`` describes output stream ``i``.
    """

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
    def max_source_duration(self) -> float | None:
        """Return the longest known duration among the source video files."""
        return max(
            (
                duration
                for file in self.source_video_files
                if (duration := file.duration) is not None
            ),
            default=None,
        )

    @property
    def default_stream_indices(self) -> frozenset[int]:
        """Return the output stream indices to mark with disposition default."""
        return get_default_stream_indices([plan.source_stream for plan in self.root])


FileConversionPlanT = TypeVar(
    "FileConversionPlanT", bound=FileConversionPlan, covariant=True
)
