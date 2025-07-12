from pathlib import Path
from typing import Annotated, Union

import logzero
import typer
from logzero import logger

from ts2mp4.ts2mp4 import ts2mp4

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
):
    if log_file is None:
        log_file = path.with_suffix(".log")
    logzero.logfile(str(log_file))

    try:
        ts2mp4(ts=path)
    except Exception:
        logger.exception("An error occurred during conversion.")
        raise typer.Exit(code=1)
