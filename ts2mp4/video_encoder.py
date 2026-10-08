"""Builds the file conversion plan for encoding video from TS to MKV."""

from typing import Self

from pydantic import model_validator

from .conversion_plan import Copy, EncodeVideo, FileConversionPlan, StreamConversionPlan
from .converted_video_file import ConvertedVideoFile
from .video_file import AudioStream, SubtitleStream, VideoFile, VideoStream

StreamConversionPlanForVideoEncoding = (
    StreamConversionPlan[VideoStream, EncodeVideo]
    | StreamConversionPlan[AudioStream, Copy]
    | StreamConversionPlan[SubtitleStream, Copy]
)


class FileConversionPlanForVideoEncoding(FileConversionPlan):
    """Represents the file conversion plan for video encoding."""

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
                "All source streams must originate from the same VideoFile."
            )
        if len({s.source_stream.index for s in self.root}) < len(self.root):
            raise ValueError("Source streams must be unique.")
        return self


VideoEncodedFile = ConvertedVideoFile[FileConversionPlanForVideoEncoding]
"""Represents a ConvertedVideoFile after video stream encoding."""


def build_file_conversion_plan_for_video_encoding(
    input_file: VideoFile, crf: int, preset: int
) -> FileConversionPlanForVideoEncoding:
    """Build the file conversion plan that encodes video and copies the rest from TS to MKV.

    Audio and subtitle streams are copied.

    Video is encoded with SVT-AV1 in 10 bit, which reduces banding even from an
    8 bit source.
    """
    encode_video = EncodeVideo(
        codec="libsvtav1",
        crf=crf,
        preset=preset,
        pix_fmt="yuv420p10le",
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
    subtitle_plans: list[StreamConversionPlanForVideoEncoding] = [
        StreamConversionPlan(
            source_stream=stream,
            conversion_method=Copy(),
        )
        for stream in sorted(input_file.valid_subtitle_streams)
    ]

    return FileConversionPlanForVideoEncoding(
        root=tuple(video_plans + audio_plans + subtitle_plans)
    )
