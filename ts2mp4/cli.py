import datetime
import platform
from enum import Enum
from pathlib import Path
from typing import Annotated, Union

import logzero
import typer
from logzero import logger

from ts2mp4 import _get_ts2mp4_version
from ts2mp4.ts2mp4 import ts2mp4


class Preset(str, Enum):
    """Enum for FFmpeg presets."""

    ultrafast = "ultrafast"
    superfast = "superfast"
    veryfast = "veryfast"
    faster = "faster"
    fast = "fast"
    medium = "medium"
    slow = "slow"
    slower = "slower"
    veryslow = "veryslow"
    placebo = "placebo"


app = typer.Typer()


@app.command()
def main(
    path: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    log_file: Annotated[
        Union[Path, None],
        typer.Option(
            help="Path to the log file. Defaults to <input_file>.log",
            file_okay=True,
            dir_okay=False,
            writable=True,
        ),
    ] = None,
    crf: Annotated[
        int, typer.Option(help="CRF value for encoding. Defaults to 22.")
    ] = 22,
    preset: Annotated[
        Preset, typer.Option(help="Encoding preset. Defaults to 'slow'.")
    ] = Preset.slow,
) -> None:
    """Convert a Transport Stream (TS) file to MP4 format."""
    if log_file is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        log_file = path.with_stem(f"{path.stem}-{timestamp}").with_suffix(".log")
    logzero.logfile(str(log_file))

    try:
        start_time = datetime.datetime.now()
        logger.info(f"Conversion Log for {path.name}")
        logger.info(f"Start Time: {start_time}")
        logger.info(f"Input File: {path.resolve()}")
        logger.info(f"Input File Size: {path.stat().st_size} bytes")

        ts_resolved = path.resolve()
        mp4 = ts_resolved.with_suffix(".mp4")
        mp4_part = ts_resolved.with_suffix(".mp4.part")

        if mp4.exists():
            logger.info(f"Output file {mp4.name} already exists. Skipping conversion.")
            return

        ts2mp4(input_file=ts_resolved, output_file=mp4_part, crf=crf, preset=preset)

        logger.info("Conversion Status: Success")

        mp4_part.replace(mp4)
        logger.info(f"Output File: {mp4.resolve()}")
        logger.info(f"Output File Size: {mp4.stat().st_size} bytes")

        end_time = datetime.datetime.now()
        logger.info(f"End Time: {end_time}")
        logger.info(f"Duration: {end_time - start_time}")
        logger.info(f"ts2mp4 Version: {_get_ts2mp4_version()}")
        logger.info(f"Python Version: {platform.python_version()}")
        logger.info(f"Platform: {platform.platform()}")
    except Exception:
        logger.exception("An error occurred during conversion.")
        raise typer.Exit(code=1)
