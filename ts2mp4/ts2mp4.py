import subprocess
from pathlib import Path


def ts2mp4(ts: Path):
    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if mp4.exists():
        return

    proc = subprocess.run(
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
            "-crf",
            "22",
            "-codec:a",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(mp4_part),
        ]
    )

    if proc.returncode == 0:
        mp4_part.replace(mp4)
