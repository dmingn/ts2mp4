"""Runs FFmpeg to write a file conversion plan into a converted video file."""

from pathlib import Path
from typing import TypeVar

from .conversion_plan import ConvertedVideoFile, FileConversionPlan
from .ffmpeg import execute_ffmpeg
from .ffmpeg_args import build_ffmpeg_args

_FileConversionPlanT = TypeVar("_FileConversionPlanT", bound=FileConversionPlan)


def execute_conversion(
    file_conversion_plan: _FileConversionPlanT, output_path: Path
) -> ConvertedVideoFile[_FileConversionPlanT]:
    """Write ``file_conversion_plan`` to ``output_path`` and return the converted file."""
    execute_ffmpeg(build_ffmpeg_args(file_conversion_plan, output_path))

    return ConvertedVideoFile(
        path=output_path, file_conversion_plan=file_conversion_plan
    )
