"""Encodes video streams from TS to MP4 (pipeline stage 1).

Output is consumed by audio_encoder when copied audio fails integrity checks.
"""

from pathlib import Path
from typing import Self

from pydantic import model_validator

from .ffmpeg import execute_ffmpeg
from .ffmpeg_args import build_ffmpeg_args
from .stream_source import (
    ConvertedVideoFile,
    Copy,
    EncodeVideo,
    StreamSource,
    StreamSources,
)
from .video_file import AudioStream, VideoFile, VideoStream

StreamSourceForVideoEncoding = (
    StreamSource[VideoStream, EncodeVideo] | StreamSource[AudioStream, Copy]
)


class StreamSourcesForVideoEncoding(StreamSources):
    """Represents the stream sources for video encoding."""

    root: tuple[StreamSourceForVideoEncoding, ...]

    @model_validator(mode="after")
    def validate_stream_presence(self) -> Self:
        """Validate the presence of at least one video and one audio stream."""
        if not self.video_stream_sources:
            raise ValueError("At least one video stream is required.")
        if not self.audio_stream_sources:
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


def _build_stream_sources(
    input_file: VideoFile, crf: int, preset: str
) -> StreamSourcesForVideoEncoding:
    """Build the stream sources for video encoding."""
    encode_video = EncodeVideo(
        codec="libx265",
        crf=crf,
        preset=preset,
        video_filter="bwdif",
        fps_mode="cfr",
    )

    video_sources: list[StreamSourceForVideoEncoding] = [
        StreamSource(
            source_stream=stream,
            conversion=encode_video,
        )
        for stream in sorted(input_file.valid_video_streams)
    ]
    audio_sources: list[StreamSourceForVideoEncoding] = [
        StreamSource(
            source_stream=stream,
            conversion=Copy(),
        )
        for stream in sorted(input_file.valid_audio_streams)
    ]

    return StreamSourcesForVideoEncoding(root=tuple(video_sources + audio_sources))


def encode_video_streams(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> VideoEncodedFile:
    """Encode video streams from TS to MP4 (audio streams are copied)."""
    stream_sources = _build_stream_sources(input_file, crf=crf, preset=preset)
    ffmpeg_args = build_ffmpeg_args(
        stream_sources=stream_sources, output_path=output_path
    )
    execute_ffmpeg(ffmpeg_args)
    return VideoEncodedFile(path=output_path, stream_sources=stream_sources)
