"""Encodes video streams from TS to MP4 (pipeline stage 1).

Output is consumed by audio_encoder when copied audio fails integrity checks.
"""

from pathlib import Path
from typing import Self

from pydantic import model_validator

from .ffmpeg import execute_ffmpeg
from .stream_disposition import build_disposition_args
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

    @property
    def source_video_file(self) -> VideoFile:
        """Return the source video file for the stream sources."""
        return next(iter(self.source_video_files))


VideoEncodedFile = ConvertedVideoFile[StreamSourcesForVideoEncoding]
"""Represents a ConvertedVideoFile after video stream encoding."""


def _build_stream_sources(input_file: VideoFile) -> StreamSourcesForVideoEncoding:
    """Build the stream sources for video encoding."""
    video_sources: list[StreamSourceForVideoEncoding] = [
        StreamSource(
            source_stream=stream,
            conversion=EncodeVideo(),
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


def _build_ffmpeg_args_from_stream_sources(
    stream_sources: StreamSourcesForVideoEncoding,
    output_path: Path,
    crf: int,
    preset: str,
) -> list[str]:
    """Build FFmpeg arguments for video encoding (TS to MP4)."""
    return (
        [
            "-hide_banner",
            "-nostats",
            "-fflags",
            "+discardcorrupt",
            "-y",
            "-i",
            str(stream_sources.source_video_file.path),
        ]
        + [
            arg
            for source in stream_sources
            for arg in ("-map", f"0:{source.source_stream.index}")
        ]
        + build_disposition_args(stream_sources)
        + [
            "-f",
            "mp4",
            "-fps_mode",
            "cfr",
            "-vf",
            "bwdif",
            "-codec:v",
            "libx265",
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-codec:a",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(output_path),
        ]
    )


def encode_video_streams(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> VideoEncodedFile:
    """Encode video streams from TS to MP4 (audio streams are copied)."""
    stream_sources = _build_stream_sources(input_file)
    ffmpeg_args = _build_ffmpeg_args_from_stream_sources(
        stream_sources=stream_sources, output_path=output_path, crf=crf, preset=preset
    )
    execute_ffmpeg(ffmpeg_args)
    return VideoEncodedFile(path=output_path, stream_sources=stream_sources)
