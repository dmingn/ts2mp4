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


def ts2mp4(ts: Path, crf: int, preset: str):
    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if mp4.exists():
        logger.info(f"Output file {mp4.name} already exists. Skipping conversion.")
        return

    ffmpeg_command = [
        "ffmpeg",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(ts),
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
        str(mp4_part),
    ]
    logger.info(f"FFmpeg Command: {' '.join(ffmpeg_command)}")

    process = subprocess.run(
        args=ffmpeg_command,
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info("Conversion Status: Success")
    logger.info("FFmpeg Stdout:\n" + process.stdout)
    logger.info("FFmpeg Stderr:\n" + process.stderr)

    verify_audio_stream_integrity(ts, mp4_part)

    mp4_part.replace(mp4)
    logger.info(f"Output File: {mp4.resolve()}")
    logger.info(f"Output File Size: {mp4.stat().st_size} bytes")
