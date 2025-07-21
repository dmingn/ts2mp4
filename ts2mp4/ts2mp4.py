from pathlib import Path

from .audio_integrity import get_mismatched_audio_stream_indices
from .ffmpeg import execute_ffmpeg


def ts2mp4(input_file: Path, output_file: Path, crf: int, preset: str) -> None:
    """Converts a Transport Stream (TS) file to MP4 format using FFmpeg.

    This function constructs and executes an FFmpeg command to perform the video
    conversion. It also logs the FFmpeg output and verifies the audio stream
    integrity of the converted file.

    Args:
    ----
        input_file: The path to the input TS file.
        output_file: The path where the output MP4 file will be saved.
        crf: The Constant Rate Factor (CRF) value for video encoding. Lower
            values result in higher quality and larger file sizes.
        preset: The encoding preset for FFmpeg. This affects the compression
            speed and efficiency (e.g., 'medium', 'fast', 'slow').

    """
    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(input_file),
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-map",
        "0:s?",
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
        "-codec:s",
        "mov_text",
        "-bsf:a",
        "aac_adtstoasc",
        str(output_file),
    ]
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    mismatched_indices = get_mismatched_audio_stream_indices(
        input_file=input_file, output_file=output_file
    )
    if mismatched_indices:
        raise RuntimeError(
            f"Audio stream integrity check failed for pairs: {mismatched_indices}"
        )
