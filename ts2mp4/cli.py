"""Command-line interface for ts2mp4."""

import datetime
import platform
from pathlib import Path
from typing import Annotated

import logzero
import typer
from logzero import logger

from ts2mp4 import _get_ts2mp4_version
from ts2mp4.ffmpeg import SubprocessFFmpegRunner
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import VideoFile


def version_callback(value: bool) -> None:
    """Print the version of the application."""
    if value:
        print(f"ts2mp4 version: {_get_ts2mp4_version()}")
        raise typer.Exit()


app = typer.Typer()


@app.command()
def main(
    path: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    log_file: Annotated[
        Path | None,
        typer.Option(
            help="Path to the log file. Defaults to <input_file>.log",
            file_okay=True,
            dir_okay=False,
            writable=True,
        ),
    ] = None,
    crf: Annotated[
        int,
        typer.Option(
            min=0,
            max=63,
            help="SVT-AV1 CRF value for encoding. Defaults to 32.",
        ),
    ] = 32,
    preset: Annotated[
        int,
        typer.Option(
            min=0,
            max=13,
            help="SVT-AV1 encoding preset. Lower is slower. Defaults to 5.",
        ),
    ] = 5,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Convert a Transport Stream (TS) file to Matroska (MKV) format."""
    if log_file is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        log_file = path.with_stem(f"{path.stem}-{timestamp}").with_suffix(".log")
    logzero.logfile(str(log_file))

    logger.info(f"ts2mp4 Version: {_get_ts2mp4_version()}")
    logger.info(f"Python Version: {platform.python_version()}")
    logger.info(f"Platform: {platform.platform()}")

    try:
        start_time = datetime.datetime.now()
        logger.info(f"Conversion Log for {path.name}")
        logger.info(f"Start Time: {start_time}")
        logger.info(f"Input File: {path.resolve()}")
        logger.info(f"Input File Size: {path.stat().st_size} bytes")

        ts_resolved = path.resolve()
        mkv = ts_resolved.with_suffix(".mkv")
        mkv_part = ts_resolved.with_suffix(".mkv.part")

        if mkv.exists():
            logger.info(f"Output file {mkv.name} already exists. Skipping conversion.")
            return

        video_file = VideoFile(path=ts_resolved)
        ts2mp4(
            input_file=video_file,
            output_path=mkv_part,
            crf=crf,
            preset=preset,
            ffmpeg_runner=SubprocessFFmpegRunner(),
        )

        logger.info("Conversion Status: Success")

        mkv_part.replace(mkv)
        logger.info(f"Output File: {mkv.resolve()}")
        logger.info(f"Output File Size: {mkv.stat().st_size} bytes")

        end_time = datetime.datetime.now()
        logger.info(f"End Time: {end_time}")
        logger.info(f"Duration: {end_time - start_time}")
    except Exception:
        logger.exception("An error occurred during conversion.")
        raise typer.Exit(code=1)
