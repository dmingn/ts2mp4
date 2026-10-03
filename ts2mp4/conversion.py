"""Runs FFmpeg to write a file conversion plan into a converted video file."""

import asyncio
from collections.abc import AsyncIterable
from pathlib import Path
from typing import TypeVar

from logzero import logger
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .conversion_plan import FileConversionPlan
from .converted_video_file import ConvertedVideoFile
from .ffmpeg import FFmpegRunner
from .ffmpeg_args import build_ffmpeg_args

_FileConversionPlanT = TypeVar("_FileConversionPlanT", bound=FileConversionPlan)


def _bar_position(out_seconds: float, total: int | None) -> int:
    """Return the bar position in whole seconds, clamped to ``[0, total]``."""
    position = max(0, round(out_seconds))
    return position if total is None else min(position, total)


async def _show_progress(
    out_seconds: AsyncIterable[float], total_duration: float | None
) -> None:
    """Consume ``out_seconds``, showing them as a progress bar on a TTY stderr.

    While the bar is shown, console log records are routed through tqdm so that
    they do not break the bar. The log file is not affected.
    """
    total = round(total_duration) if total_duration is not None else None

    with (
        logging_redirect_tqdm(loggers=[logger]),
        tqdm(total=total, desc="Encoding", unit="s", disable=None) as bar,
    ):
        async for seconds in out_seconds:
            bar.update(_bar_position(seconds, total) - bar.n)


def execute_conversion(
    file_conversion_plan: _FileConversionPlanT,
    output_path: Path,
    ffmpeg_runner: FFmpegRunner,
) -> ConvertedVideoFile[_FileConversionPlanT]:
    """Write ``file_conversion_plan`` to ``output_path`` and return the converted file."""
    asyncio.run(
        _show_progress(
            ffmpeg_runner.stream_out_seconds(
                build_ffmpeg_args(file_conversion_plan, output_path)
            ),
            file_conversion_plan.max_source_duration,
        )
    )

    return ConvertedVideoFile(
        path=output_path, file_conversion_plan=file_conversion_plan
    )
