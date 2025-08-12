"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger

from .audio_reencoder import re_encode_mismatched_audio_streams
from .ffmpeg import execute_ffmpeg
from .stream_integrity import verify_streams
from .video_file import ConversionType, ConvertedVideoFile, StreamSource, VideoFile


def _build_ffmpeg_conversion_args(
    output_path: Path,
    crf: int,
    preset: str,
    stream_sources: dict[int, StreamSource],
) -> list[str]:
    """Build FFmpeg arguments for the initial TS to MP4 conversion."""
    input_file = next(iter(stream_sources.values())).source_video_file.path
    return (
        [
            "-hide_banner",
            "-nostats",
            "-fflags",
            "+discardcorrupt",
            "-y",
            "-i",
            str(input_file),
        ]
        + [
            arg
            for source in stream_sources.values()
            for arg in ("-map", f"0:{source.source_stream_index}")
        ]
        + [
            # "-map",
            # "0:s?",
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
            # "-codec:s",
            # "mov_text",
            "-bsf:a",
            "aac_adtstoasc",
            str(output_path),
        ]
    )


def _perform_initial_conversion(
    input_file: VideoFile, output_path: Path, crf: int, preset: str
) -> ConvertedVideoFile:
    """Perform the initial FFmpeg conversion from TS to MP4."""
    video_streams = [
        s for s in input_file.media_info.streams if s.codec_type == "video"
    ]
    audio_streams = input_file.valid_audio_streams
    all_streams = video_streams + audio_streams

    stream_sources = {
        i: StreamSource(
            source_video_file=input_file,
            source_stream_index=stream.index,
            conversion_type=ConversionType.CONVERTED,
        )
        for i, stream in enumerate(all_streams)
    }

    ffmpeg_args = _build_ffmpeg_conversion_args(
        output_path, crf, preset, stream_sources
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
