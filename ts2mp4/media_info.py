"""A module for getting media information."""

import json
from functools import cache
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ffmpeg import execute_ffprobe


class Stream(BaseModel):
    """A class to hold information about a single stream."""

    model_config = ConfigDict(frozen=True)

    index: int
    codec_type: Optional[str] = None
    codec_name: Optional[str] = None
    profile: Optional[str] = None
    bit_rate: Optional[int] = None
    channels: Optional[int] = None
    sample_rate: Optional[int] = None


class Format(BaseModel):
    """A class to hold information about the format of a media file."""

    model_config = ConfigDict(frozen=True)

    format_name: Optional[str] = None


class MediaInfo(BaseModel):
    """A class to hold media information."""

    model_config = ConfigDict(frozen=True)

    streams: tuple[Stream, ...] = Field(default_factory=tuple)
    format: Optional[Format] = None

    @field_validator("streams", mode="before")
    @classmethod
    def sort_streams(cls, v: Any) -> Union[list[Any], Any]:
        """Sorts a list of streams by their index."""
        if v is not None and isinstance(v, list):
            return sorted(
                v,
                key=lambda stream_data: (
                    stream_data.index
                    if isinstance(stream_data, Stream)
                    else stream_data["index"]
                ),
            )
        return v

    @field_validator("streams", mode="after")
    @classmethod
    def validate_stream_indices(cls, streams: tuple[Stream, ...]) -> tuple[Stream, ...]:
        """Validate that stream indices match their position in the tuple."""
        for i, stream in enumerate(streams):
            if stream.index != i:
                raise ValueError(
                    f"Stream index {stream.index} does not match tuple index {i}"
                )
        return streams


@cache
def _get_media_info_cached(file_path: Path, _mtime: float, _size: int) -> MediaInfo:
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


def get_media_info(file_path: Path) -> MediaInfo:
    """Return media information for a given file.

    Args:
    ----
        file_path: The path to the input file.

    Returns
    -------
        A MediaInfo object with the media information.

    Raises
    ------
        RuntimeError: If ffprobe fails to get media information.

    """
    resolved_path = file_path.resolve(strict=True)
    stat = resolved_path.stat()
    return _get_media_info_cached(resolved_path, stat.st_mtime, stat.st_size)
