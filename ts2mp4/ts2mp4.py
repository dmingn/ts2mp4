"""The main module of the ts2mp4 package."""

from pathlib import Path

from logzero import logger

from .audio_channels import find_streams_requiring_fixed_surround
from .audio_encoder import build_file_conversion_plan_for_audio_encoding
from .conversion import execute_conversion
from .conversion_plan import FileConversionPlan
from .converted_video_file import ConvertedVideoFile
from .ffmpeg import FFmpegRunner, is_libfdk_aac_available
from .quality_check import check_audio_quality
from .stream_integrity import IntegrityReport, check_integrity
from .stream_timing import check_timing
from .video_encoder import build_file_conversion_plan_for_video_encoding
from .video_file import SubtitleStream, VideoFile


def _verify_timing(converted_file: ConvertedVideoFile[FileConversionPlan]) -> None:
    """Raise if a re-encoded stream of ``converted_file`` is shifted in time."""
    logger.info(f"Verifying re-encoded stream timing for {converted_file.path.name}")
    timing_report = check_timing(converted_file)
    if not timing_report.is_ok:
        raise RuntimeError(
            "Timing check failed for output streams at indices "
            f"{sorted(timing_report.shifted_output_indices)} "
            f"in {converted_file.path.name}"
        )


def _verify_subtitle_integrity(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    integrity_report: IntegrityReport,
) -> None:
    """Raise if a copied subtitle stream of ``converted_file`` does not match its source.

    Subtitles cannot be re-encoded, so the audio encoding pass copies them from
    ``converted_file`` and its integrity check cannot detect this mismatch.
    """
    mismatched_subtitle_indices = sorted(
        stream.index
        for stream in converted_file.streams
        if isinstance(stream, SubtitleStream)
        and stream.index in integrity_report.mismatched_output_indices
    )
    if mismatched_subtitle_indices:
        raise RuntimeError(
            "Subtitle integrity check failed for output streams at indices "
            f"{mismatched_subtitle_indices} in {converted_file.path.name}"
        )


def ts2mp4(
    input_file: VideoFile,
    output_path: Path,
    crf: int,
    preset: int,
    ffmpeg_runner: FFmpegRunner,
) -> None:
    """Convert a Transport Stream (TS) file to Matroska (MKV) format using FFmpeg.

    This function orchestrates the video conversion process, including video
    encoding, audio stream integrity verification, and conditional audio encoding.

    Args:
    ----
        input_file: The VideoFile object for the input TS file.
        output_path: The path where the output MKV file will be saved.
        crf: The Constant Rate Factor (CRF) value for video encoding. Lower
            values result in higher quality and larger file sizes.
        preset: The SVT-AV1 encoding preset from 0 to 13. Lower values are
            slower and compress more efficiently.
        ffmpeg_runner: The FFmpegRunner used to run ffmpeg.

    """
    logger.info(f"Analyzing audio channel layouts of {input_file.path.name}")
    fixed_surround_source_indices = find_streams_requiring_fixed_surround(input_file)
    if fixed_surround_source_indices:
        logger.warning(
            "Audio streams at indices "
            f"{sorted(fixed_surround_source_indices)} contain 5.1ch frames but "
            "are not consistently 5.1ch as declared. They will be encoded as "
            "fixed 5.1ch."
        )

    video_encoded_file = execute_conversion(
        build_file_conversion_plan_for_video_encoding(
            input_file, crf=crf, preset=preset
        ),
        output_path,
        ffmpeg_runner,
    )
    _verify_timing(video_encoded_file)

    logger.info(f"Verifying copied stream integrity for {video_encoded_file.path.name}")
    video_encoded_integrity_report = check_integrity(video_encoded_file, ffmpeg_runner)
    if video_encoded_integrity_report.is_ok:
        logger.info(
            "Copied stream integrity verified successfully. "
            "All audio parameters, frame hashes and timestamps match."
        )
    else:
        logger.warning(
            "Copied stream integrity check failed for output streams at indices "
            f"{sorted(video_encoded_integrity_report.mismatched_output_indices)}"
        )
    _verify_subtitle_integrity(video_encoded_file, video_encoded_integrity_report)

    if video_encoded_integrity_report.is_ok and not fixed_surround_source_indices:
        return

    logger.info("Attempting to encode audio streams.")
    temp_output_file = output_path.with_suffix(output_path.suffix + ".temp")
    audio_encoded_file = execute_conversion(
        build_file_conversion_plan_for_audio_encoding(
            original_file=input_file,
            encoded_file=video_encoded_file,
            integrity_report=video_encoded_integrity_report,
            fixed_surround_source_indices=fixed_surround_source_indices,
            libfdk_aac_available=is_libfdk_aac_available(ffmpeg_runner),
        ),
        temp_output_file,
        ffmpeg_runner,
    )
    _verify_timing(audio_encoded_file)

    logger.info(f"Verifying copied stream integrity for {audio_encoded_file.path.name}")
    audio_encoded_integrity_report = check_integrity(audio_encoded_file, ffmpeg_runner)
    if not audio_encoded_integrity_report.is_ok:
        raise RuntimeError(
            "Stream integrity check failed after audio encoding for output "
            f"streams at indices {sorted(audio_encoded_integrity_report.mismatched_output_indices)} "
            f"in {audio_encoded_file.path.name}"
        )
    logger.info(
        "Copied stream integrity verified successfully. "
        "All audio parameters, frame hashes and timestamps match."
    )

    audio_quality_report = check_audio_quality(audio_encoded_file, ffmpeg_runner)
    if not audio_quality_report.is_ok:
        raise RuntimeError(
            "Audio quality check failed for output streams at indices "
            f"{sorted(audio_quality_report.degraded_output_indices)} "
            f"in {audio_encoded_file.path.name}"
        )

    temp_output_file.replace(output_path)
    logger.info(
        f"Successfully encoded audio for {output_path.name} and replaced original."
    )
