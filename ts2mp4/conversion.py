"""Runs FFmpeg to write stream sources into a converted video file."""

from pathlib import Path
from typing import TypeVar

from .ffmpeg import execute_ffmpeg
from .ffmpeg_args import build_ffmpeg_args
from .stream_source import ConvertedVideoFile, StreamSources

_StreamSourcesT = TypeVar("_StreamSourcesT", bound=StreamSources)


def execute_conversion(
    stream_sources: _StreamSourcesT, output_path: Path
) -> ConvertedVideoFile[_StreamSourcesT]:
    """Write ``stream_sources`` to ``output_path`` and return the converted file."""
    execute_ffmpeg(build_ffmpeg_args(stream_sources, output_path))

    return ConvertedVideoFile(path=output_path, stream_sources=stream_sources)
