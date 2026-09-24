"""ffprobe JSON output schema and probing."""

import json
from functools import cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .ffmpeg import execute_ffprobe


class FFprobeStream(BaseModel):
    """A single stream entry from ffprobe ``-show_streams`` JSON."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    index: int
    codec_type: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec_name: Optional[str] = None
    profile: Optional[str] = None
    bit_rate: Optional[int] = None
    channels: Optional[int] = None
    sample_rate: Optional[int] = None


class FFprobeFormat(BaseModel):
    """A format entry from ffprobe ``-show_format`` JSON."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    format_name: Optional[str] = None
    duration: Optional[float] = None


class FFprobeOutput(BaseModel):
    """Top-level ffprobe ``-of json`` output."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    streams: tuple[FFprobeStream, ...] = Field(default_factory=tuple)
    format: Optional[FFprobeFormat] = None


@cache
def _probe_file_cached(file_path: Path, _mtime: float, _size: int) -> FFprobeOutput:
    ffprobe_args = [
        "-hide_banner",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(file_path),
    ]
    result = execute_ffprobe(ffprobe_args)
    data = json.loads(result.stdout.decode("utf-8"))
    return FFprobeOutput.model_validate(data)


def probe_file(file_path: Path) -> FFprobeOutput:
    """Return ffprobe output for a given file.

    Args:
    ----
        file_path: The path to the input file.

    Returns
    -------
        An FFprobeOutput object with the probed information.

    Raises
    ------
        FFmpegProcessError: If ffprobe fails to get media information.
    """
    resolved_path = file_path.resolve(strict=True)
    stat = resolved_path.stat()
    return _probe_file_cached(resolved_path, stat.st_mtime, stat.st_size)
