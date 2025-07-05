from pathlib import Path
from typing import Annotated

import typer

from ts2mp4.ts2mp4 import ts2mp4

app = typer.Typer()


@app.command()
def main(
    path: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
):
    ts2mp4(ts=path)
