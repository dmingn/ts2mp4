import argparse
import subprocess
from pathlib import Path


def ts2mp4(ts: Path):
    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")

    if not mp4.exists():
        subprocess.run(
            args=[
                "ffmpeg",
                "-fflags",
                "+discardcorrupt",
                "-y",
                "-i",
                str(ts),
                "-f",
                "mp4",
                "-vsync",
                "1",
                "-vf",
                "bwdif",
                "-codec:v",
                "libx265",
                "-codec:a",
                "copy",
                "-bsf:a",
                "aac_adtstoasc",
                "-map",
                "0",
                str(mp4),
            ]
        )


def job(path: Path):
    if path.is_dir():
        for ts in path.glob("*.ts"):
            ts2mp4(ts)
    elif path.suffix == ".ts":
        ts2mp4(path)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    job(path=args.path)
