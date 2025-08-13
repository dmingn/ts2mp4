"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger
from typing_extensions import Self

from .audio_reencoder import re_encode_mismatched_audio_streams
from .ffmpeg import execute_ffmpeg
from .stream_integrity import verify_streams
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


def _perform_initial_conversion(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> ConvertedVideoFile:
    """Perform the initial FFmpeg conversion from TS to MP4."""
    stream_sources = _build_stream_sources(input_file)
    ffmpeg_args = _build_ffmpeg_args_from_stream_sources(
        stream_sources=stream_sources, output_path=output_path, crf=crf, preset=preset
    )
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")
    return ConvertedVideoFile(path=output_path, stream_sources=stream_sources)


def ts2mp4(input_file: VideoFile, output_path: Path, crf: int, preset: str) -> None:
    """Convert a Transport Stream (TS) file to MP4 format using FFmpeg.

    This function orchestrates the video conversion process, including initial FFmpeg
    execution, audio stream integrity verification, and conditional re-encoding.

    Args:
    ----
        input_file: The VideoFile object for the input TS file.
        output_path: The path where the output MP4 file will be saved.
        crf: The Constant Rate Factor (CRF) value for video encoding. Lower
            values result in higher quality and larger file sizes.
        preset: The encoding preset for FFmpeg. This affects the compression
            speed and efficiency (e.g., 'medium', 'fast', 'slow').

    """
    output_file = _perform_initial_conversion(input_file, output_path, crf, preset)

    try:
        verify_streams(
            input_file=input_file,
            output_file=output_file,
            stream_type="audio",
        )
    except RuntimeError as e:
        logger.warning(f"Audio integrity check failed: {e}")
        logger.info("Attempting to re-encode mismatched audio streams.")
        temp_output_file = output_path.with_suffix(output_path.suffix + ".temp")
        re_encode_mismatched_audio_streams(
            original_file=input_file,
            encoded_file=output_file,
            output_file=temp_output_file,
        )
        temp_output_file.replace(output_path)
        logger.info(
            f"Successfully re-encoded audio for {output_path.name} and replaced original."
        )
