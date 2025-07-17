import subprocess
from pathlib import Path

from logzero import logger

from .audio_integrity import verify_audio_stream_integrity


def ts2mp4(input_file: Path, output_file: Path, crf: int, preset: str):
    """Converts a Transport Stream (TS) file to MP4 format using FFmpeg.

    This function constructs and executes an FFmpeg command to perform the video
    conversion. It also logs the FFmpeg output and verifies the audio stream
    integrity of the converted file.

    Args:
        input_file: The path to the input TS file.
        output_file: The path where the output MP4 file will be saved.
        crf: The Constant Rate Factor (CRF) value for video encoding. Lower
            values result in higher quality and larger file sizes.
        preset: The encoding preset for FFmpeg. This affects the compression
            speed and efficiency (e.g., 'medium', 'fast', 'slow').
    """
    ffmpeg_command = [
        "ffmpeg",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(input_file),
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
        str(output_file),
    ]
    logger.info(f"FFmpeg Command: {' '.join(ffmpeg_command)}")

    process = subprocess.run(
        args=ffmpeg_command,
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info("FFmpeg Stdout:\n" + process.stdout)
    logger.info("FFmpeg Stderr:\n" + process.stderr)

    verify_audio_stream_integrity(input_file=input_file, output_file=output_file)
