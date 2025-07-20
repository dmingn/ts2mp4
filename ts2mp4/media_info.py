import json
from functools import cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .ffmpeg import execute_ffprobe


class Stream(BaseModel):
    """A class to hold information about a single stream."""

    model_config = ConfigDict(frozen=True)

    codec_type: Optional[str] = None


class Format(BaseModel):
    """A class to hold information about the format of a media file."""

    model_config = ConfigDict(frozen=True)

    format_name: Optional[str] = None


class MediaInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    streams: tuple[Stream, ...] = Field(default_factory=tuple)
    format: Optional[Format] = None


@cache
def get_media_info(file_path: Path) -> MediaInfo:
    """Returns media information for a given file.

    Args:
    ----
        file_path: The path to the input file.

    Returns:
    -------
        A MediaInfo object with the media information.

    Raises:
    ------
        RuntimeError: If ffprobe fails to get media information.

    """
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
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed to get media information for {file_path}. "
            f"Return code: {result.returncode}"
        )
    data = json.loads(result.stdout.decode("utf-8"))
    return MediaInfo.model_validate(data)
