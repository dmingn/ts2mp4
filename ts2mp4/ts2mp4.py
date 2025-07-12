import importlib.metadata
import subprocess
from pathlib import Path

from logzero import logger

from .audio_integrity import verify_audio_stream_integrity


def _get_ts2mp4_version() -> str:
    try:
        return importlib.metadata.version("ts2mp4")
    except importlib.metadata.PackageNotFoundError:
        return "Unknown"


def ts2mp4(input_file: Path, output_file: Path, crf: int, preset: str):
    ffmpeg_command = [
        "ffmpeg",
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
