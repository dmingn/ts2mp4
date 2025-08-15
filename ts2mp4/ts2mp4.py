"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger

from .audio_reencoder import AudioReEncodedVideoFile, re_encode_mismatched_audio_streams
from .initial_converter import InitiallyConvertedVideoFile, perform_initial_conversion
from .quality_check import get_audio_quality_metrics
from .stream_integrity import verify_copied_streams
from .video_file import ConvertedVideoFile, VideoFile


def ts2mp4(input_file: VideoFile, output_path: Path, crf: int, preset: str) -> None:
    """Convert a Transport Stream (TS) file to MP4 format using FFmpeg.

    This function orchestrates the video conversion process, including initial FFmpeg
    execution, conditional audio stream re-encoding, and final stream verification
    and quality assessment.

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

    final_video_file = _re_encode_audio_if_necessary(
        original_file=input_file,
        encoded_file=initially_converted_video_file,
        output_path=output_path,
    )

    logger.info(f"Verifying streams for {final_video_file.path.name}...")
    try:
        verify_copied_streams(converted_file=final_video_file)
        logger.info("All stream hashes match.")
    except RuntimeError as e:
        logger.error(f"Stream verification failed for the final file: {e}")

    logger.info(f"Getting audio quality metrics for {final_video_file.path.name}...")
    quality_metrics = get_audio_quality_metrics(final_video_file)
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


def _re_encode_audio_if_necessary(
    original_file: VideoFile,
    encoded_file: InitiallyConvertedVideoFile,
    output_path: Path,
) -> ConvertedVideoFile:
    """Re-encode audio streams if necessary and return the final video file."""
    try:
        verify_copied_streams(converted_file=encoded_file)
        logger.info("No audio re-encoding is necessary.")
        return encoded_file
    except RuntimeError as e:
        logger.warning(f"Audio integrity check failed: {e}")
        logger.info("Attempting to re-encode mismatched audio streams.")

        temp_output_file = output_path.with_suffix(output_path.suffix + ".temp")
        re_encoded_file = re_encode_mismatched_audio_streams(
            original_file=original_file,
            encoded_file=encoded_file,
            output_file=temp_output_file,
        )

        if re_encoded_file:
            temp_output_file.replace(output_path)
            logger.info(
                "Successfully re-encoded audio and replaced the original output file."
            )
            return AudioReEncodedVideoFile(
                path=output_path, stream_sources=re_encoded_file.stream_sources
            )

        logger.warning(
            "Audio re-encoding was attempted but did not produce a new file."
        )
        return encoded_file
