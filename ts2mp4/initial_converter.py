"""Handles the initial conversion from TS to MP4."""

from pathlib import Path

from typing_extensions import Self

from .ffmpeg import execute_ffmpeg
from .video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)


class StreamSourcesForInitialConversion(StreamSources):
    """Represents the stream sources for the initial conversion."""

    def __new__(cls, stream_sources: StreamSources) -> Self:
        """Initialize the StreamSourcesForInitialConversion."""
        # Stream sources must have at least one video stream
        if not stream_sources.video_stream_sources:
            raise ValueError("At least one video stream is required.")

        # Stream sources must have at least one audio stream
        if not stream_sources.audio_stream_sources:
            raise ValueError("At least one audio stream is required.")

        # All video streams must be converted
        if not all(
            s.conversion_type == ConversionType.CONVERTED
            for s in stream_sources.video_stream_sources
        ):
            raise ValueError("All video streams must be converted.")

        # All audio streams must be copied
        if not all(
            s.conversion_type == ConversionType.COPIED
            for s in stream_sources.audio_stream_sources
        ):
            raise ValueError("All audio streams must be copied.")

        # Stream source must not have any other types
        if not all(
            s.source_stream.codec_type in ["video", "audio"] for s in stream_sources
        ):
            raise ValueError("Stream sources must only contain video or audio streams.")

        # All stream sources must originate from the same VideoFile
        if len(stream_sources.source_video_files) != 1:
            raise ValueError(
                "All stream sources must originate from the same VideoFile."
            )

        return super().__new__(cls, stream_sources)

    @property
    def source_video_file(self) -> VideoFile:
        """Return the source video file for the stream sources."""
        return self[0].source_video_file


class InitiallyConvertedVideoFile(ConvertedVideoFile):
    """Represents a ConvertedVideoFile that has undergone the initial conversion."""

    stream_sources: StreamSourcesForInitialConversion


def _build_stream_sources(input_file: VideoFile) -> StreamSourcesForInitialConversion:
    """Build the stream sources for the initial conversion."""
    stream_sources = StreamSources(
        StreamSource(
            source_video_file=input_file,
            source_stream_index=stream.index,
            conversion_type=(
                ConversionType.CONVERTED
                if stream.codec_type == "video"
                else ConversionType.COPIED
            ),
        )
        for stream in sorted(input_file.valid_streams, key=lambda s: s.index)
        if stream.codec_type in ["video", "audio"]
    )

    return StreamSourcesForInitialConversion(stream_sources)


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
            for arg in ("-map", f"0:{source.source_stream_index}")
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
