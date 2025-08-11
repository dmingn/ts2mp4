"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger

from .audio_reencoder import re_encode_mismatched_audio_streams
from .ffmpeg import execute_ffmpeg
from .stream_integrity import verify_streams
from .video_file import VideoFile


def ts2mp4(input_file: VideoFile, output_file: Path, crf: int, preset: str) -> None:
    """Convert a Transport Stream (TS) file to MP4 format using FFmpeg.

    This function constructs and executes an FFmpeg command to perform the video
    conversion. It also logs the FFmpeg output and verifies the audio stream
    integrity of the converted file. If the audio stream integrity check fails,
    it attempts to re-encode the mismatched audio streams.

    Args:
    ----
        input_file: The VideoFile object for the input TS file.
        output_file: The path where the output MP4 file will be saved.
        crf: The Constant Rate Factor (CRF) value for video encoding. Lower
            values result in higher quality and larger file sizes.
        preset: The encoding preset for FFmpeg. This affects the compression
            speed and efficiency (e.g., 'medium', 'fast', 'slow').

    """
    ffmpeg_args = (
        [
            "-hide_banner",
            "-nostats",
            "-fflags",
            "+discardcorrupt",
            "-y",
            "-i",
            str(input_file.path),
            "-map",
            "0:v",
        ]
        + [
            arg
            for stream in input_file.valid_audio_streams
            for arg in ("-map", f"0:{stream.index}")
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
            str(output_file),
        ]
    )
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    output_file_video_file = VideoFile(path=output_file)
    try:
        verify_streams(
            input_file=input_file,
            output_file=output_file_video_file,
            stream_type="audio",
        )
    except RuntimeError as e:
        logger.warning(f"Audio integrity check failed: {e}")
        logger.info("Attempting to re-encode mismatched audio streams.")
        temp_output_file = output_file.with_suffix(output_file.suffix + ".temp")
        re_encode_mismatched_audio_streams(
            original_file=input_file,
            encoded_file=output_file_video_file,
            output_file=temp_output_file,
        )
        temp_output_file.replace(output_file)
        logger.info(
            f"Successfully re-encoded audio for {output_file.name} and replaced original."
        )
