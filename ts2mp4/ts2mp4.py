"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger

from .audio_reencoder import re_encode_mismatched_audio_streams
from .initial_converter import perform_initial_conversion
from .quality_check import check_audio_quality
from .stream_integrity import verify_copied_streams
from .video_file import VideoFile


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
    initially_converted_video_file = perform_initial_conversion(
        input_file, output_path, crf, preset
    )

    try:
        verify_copied_streams(converted_file=initially_converted_video_file)
    except RuntimeError as e:
        logger.warning(f"Audio integrity check failed: {e}")
        logger.info("Attempting to re-encode mismatched audio streams.")
        temp_output_file = output_path.with_suffix(output_path.suffix + ".temp")
        re_encoded_file = re_encode_mismatched_audio_streams(
            original_file=input_file,
            encoded_file=initially_converted_video_file,
            output_file=temp_output_file,
        )
        if re_encoded_file:
            verify_copied_streams(re_encoded_file)
            quality_metrics = check_audio_quality(re_encoded_file)
            for stream_index, metrics in quality_metrics.items():
                log_parts = []
                if metrics.apsnr is not None:
                    log_parts.append(f"APSNR={metrics.apsnr:.2f}dB")
                if metrics.asdr is not None:
                    log_parts.append(f"ASDR={metrics.asdr:.2f}dB")
                if log_parts:
                    logger.info(
                        f"Audio quality for stream {stream_index}: {', '.join(log_parts)}"
                    )
            temp_output_file.replace(output_path)
            logger.info(
                f"Successfully re-encoded audio for {output_path.name} and replaced original."
            )
