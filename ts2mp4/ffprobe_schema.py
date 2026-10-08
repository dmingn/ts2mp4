"""ffprobe JSON output schema and probing."""

import json
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .ffmpeg import execute_ffprobe
from .ffmpeg_input_args import build_input_args


def _seconds_from_duration_tag(value: Any) -> Any:
    """Convert a ``HH:MM:SS.nnnnnnnnn`` duration tag into seconds."""
    if not isinstance(value, str):
        return value

    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


class FFprobeStreamTags(BaseModel):
    """The tags of a stream entry from ffprobe ``-show_streams`` JSON."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    duration: Annotated[
        Optional[float], BeforeValidator(_seconds_from_duration_tag)
    ] = Field(default=None, alias="DURATION")


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
    tags: FFprobeStreamTags = Field(default_factory=FFprobeStreamTags)


class FFprobeFormat(BaseModel):
    """A format entry from ffprobe ``-show_format`` JSON."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    format_name: Optional[str] = None
    start_time: Optional[float] = None
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
        *build_input_args(file_path),
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
