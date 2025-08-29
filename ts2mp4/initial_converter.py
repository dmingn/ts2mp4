"""Handles the initial conversion from TS to MP4."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from .ffmpeg import execute_ffmpeg
from .media_info import AudioStream, VideoStream
from .video_file import (
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)

StreamSourceForInitialConversion = (
    StreamSource[VideoStream, Literal["converted"]]
    | StreamSource[AudioStream, Literal["copied"]]
)


class StreamSourcesForInitialConversion(StreamSources):
    """Represents the stream sources for the initial conversion."""

    root: tuple[StreamSourceForInitialConversion, ...]

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
        if len(set(s.source_stream for s in self.root)) < len(self.root):
            raise ValueError("Source streams must be unique.")
        return self

    @property
    def source_video_file(self) -> VideoFile:
        """Return the source video file for the stream sources."""
        return next(iter(self.source_video_files))


class InitiallyConvertedVideoFile(ConvertedVideoFile):
    """Represents a ConvertedVideoFile that has undergone the initial conversion."""

    stream_sources: StreamSourcesForInitialConversion


def _build_stream_sources(input_file: VideoFile) -> StreamSourcesForInitialConversion:
    """Build the stream sources for the initial conversion."""
    video_sources: list[StreamSourceForInitialConversion] = [
        StreamSource(
            source_video_path=input_file.path,
            source_stream=stream,
            conversion_type="converted",
        )
        for stream in input_file.valid_video_streams
    ]
    audio_sources: list[StreamSourceForInitialConversion] = [
        StreamSource(
            source_video_path=input_file.path,
            source_stream=stream,
            conversion_type="copied",
        )
        for stream in input_file.valid_audio_streams
    ]

    return StreamSourcesForInitialConversion(root=tuple(video_sources + audio_sources))


def _build_ffmpeg_args_from_stream_sources(
    stream_sources: StreamSourcesForInitialConversion,
    output_path: Path,
    crf: int,
    preset: str,
) -> list[str]:
    """Build FFmpeg arguments for the initial TS to MP4 conversion."""
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
        + [
            "-f",
            "mp4",
            "-vsync",
            "1",
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


def perform_initial_conversion(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> InitiallyConvertedVideoFile:
    """Perform the initial FFmpeg conversion from TS to MP4."""
    stream_sources = _build_stream_sources(input_file)
    ffmpeg_args = _build_ffmpeg_args_from_stream_sources(
        stream_sources=stream_sources, output_path=output_path, crf=crf, preset=preset
    )
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")
    return InitiallyConvertedVideoFile(path=output_path, stream_sources=stream_sources)
