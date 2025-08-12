"""The main module of the ts2mp4 package."""

from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple

from logzero import logger

from .audio_reencoder import re_encode_mismatched_audio_streams
from .ffmpeg import execute_ffmpeg
from .stream_integrity import verify_streams
from .video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


class ConversionResult(NamedTuple):
    """A tuple containing the results of the conversion preparation."""

    stream_sources: Mapping[int, StreamSource]
    ffmpeg_args: list[str]


def _prepare_initial_conversion(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> ConversionResult:
    """Prepare arguments and stream sources for the initial conversion."""
    video_sources = {
        i: StreamSource(
            source_video_file=input_file,
            source_stream_index=stream.index,
            conversion_type=ConversionType.CONVERTED,
        )
        for i, stream in enumerate(input_file.video_streams)
    }
    audio_sources = {
        len(video_sources) + i: StreamSource(
            source_video_file=input_file,
            source_stream_index=stream.index,
            conversion_type=ConversionType.COPIED,
        )
        for i, stream in enumerate(input_file.valid_audio_streams)
    }
    stream_sources = {**video_sources, **audio_sources}

    map_args = [
        arg
        for i in sorted(stream_sources.keys())
        for arg in ("-map", f"0:{stream_sources[i].source_stream_index}")
    ]

    ffmpeg_args = (
        [
            "-hide_banner",
            "-nostats",
            "-fflags",
            "+discardcorrupt",
            "-y",
            "-i",
            str(input_file.path),
        ]
        + map_args
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
    return ConversionResult(
        stream_sources=MappingProxyType(stream_sources), ffmpeg_args=ffmpeg_args
    )


def _perform_initial_conversion(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> ConvertedVideoFile:
    """Perform the initial FFmpeg conversion from TS to MP4."""
    result = _prepare_initial_conversion(input_file, output_path, crf, preset)
    ffmpeg_result = execute_ffmpeg(result.ffmpeg_args)
    if ffmpeg_result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {ffmpeg_result.returncode}")
    return ConvertedVideoFile(path=output_path, stream_sources=result.stream_sources)


def ts2mp4(input_file: VideoFile, output_path: Path, crf: int, preset: str) -> None:
    """Convert a Transport Stream (TS) file to MP4 format using FFmpeg."""
    output_file = _perform_initial_conversion(input_file, output_path, crf, preset)

    try:
        verify_streams(
            input_file=input_file, output_file=output_file, stream_type="audio"
        )
    except RuntimeError as e:
        logger.warning(f"Audio integrity check failed: {e}")
        logger.info("Attempting to re-encode mismatched audio streams.")
        temp_output_file = output_path.with_suffix(output_path.suffix + ".temp")
        re_encoded_file = re_encode_mismatched_audio_streams(
            original_file=input_file,
            encoded_file=output_file,
            output_file=temp_output_file,
        )
        if re_encoded_file:
            temp_output_file.replace(output_path)
            logger.info(
                "Successfully re-encoded audio for "
                f"{output_path.name} and replaced original."
            )
