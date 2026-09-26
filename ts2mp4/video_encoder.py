"""Builds the stream sources for encoding video from TS to MP4."""

from typing import Self

from pydantic import model_validator

from .stream_source import (
    ConvertedVideoFile,
    Copy,
    EncodeVideo,
    StreamConversionPlan,
    StreamSources,
)
from .video_file import AudioStream, VideoFile, VideoStream

StreamConversionPlanForVideoEncoding = (
    StreamConversionPlan[VideoStream, EncodeVideo]
    | StreamConversionPlan[AudioStream, Copy]
)


class StreamSourcesForVideoEncoding(StreamSources):
    """Represents the stream sources for video encoding."""

    root: tuple[StreamConversionPlanForVideoEncoding, ...]

    @model_validator(mode="after")
    def validate_stream_presence(self) -> Self:
        """Validate the presence of at least one video and one audio stream."""
        if not self.video_stream_plans:
            raise ValueError("At least one video stream is required.")
        if not self.audio_stream_plans:
            raise ValueError("At least one audio stream is required.")
        return self

    @model_validator(mode="after")
    def validate_source_uniqueness(self) -> Self:
        """Validate that all streams come from the same file and are unique."""
        if len(self.source_video_files) != 1:
            raise ValueError(
                "All stream sources must originate from the same VideoFile."
            )
        if len({s.source_stream.index for s in self.root}) < len(self.root):
            raise ValueError("Source streams must be unique.")
        return self


VideoEncodedFile = ConvertedVideoFile[StreamSourcesForVideoEncoding]
"""Represents a ConvertedVideoFile after video stream encoding."""


def build_stream_sources_for_video_encoding(
    input_file: VideoFile, crf: int, preset: str
) -> StreamSourcesForVideoEncoding:
    """Build the stream sources that encode video and copy audio from TS to MP4."""
    encode_video = EncodeVideo(
        codec="libx265",
        crf=crf,
        preset=preset,
        video_filter="bwdif",
        fps_mode="cfr",
    )

    video_plans: list[StreamConversionPlanForVideoEncoding] = [
        StreamConversionPlan(
            source_stream=stream,
            conversion_method=encode_video,
        )
        for stream in sorted(input_file.valid_video_streams)
    ]
    audio_plans: list[StreamConversionPlanForVideoEncoding] = [
        StreamConversionPlan(
            source_stream=stream,
            conversion_method=Copy(),
        )
        for stream in sorted(input_file.valid_audio_streams)
    ]

    return StreamSourcesForVideoEncoding(root=tuple(video_plans + audio_plans))
