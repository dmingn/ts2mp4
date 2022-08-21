import re
import subprocess
from pathlib import Path
from typing import Optional


def _parse_duration_expression(dur_expr: str) -> float:
    match = re.fullmatch(
        r"(((?P<hour>\d+):)?(?P<minute>[0-5]?[0-9]):)?(?P<second>[0-5]?[0-9](\.(?P<microsecond>\d+))?)",
        dur_expr,
    )

    if not match:
        raise ValueError

    return (
        int(match.group("hour") or 0) * 3600
        + int(match.group("minute") or 0) * 60
        + float(match.group("second"))
    )


def ts2mp4(ts: Path, ss: Optional[str], to: Optional[str]):
    ss_ = _parse_duration_expression(ss) if ss else None
    to_ = _parse_duration_expression(to) if to else None
    if ss_ and to_:
        to_ -= ss_

    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if not mp4.exists():
        proc = subprocess.run(
            args=(
                [
                    "ffmpeg",
                    "-fflags",
                    "+discardcorrupt",
                    "-y",
                ]
                + (["-ss", str(ss_)] if ss_ else [])
                + [
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
                ]
                + (["-to", str(to_)] if to_ else [])
                + [
                    str(mp4_part),
                ]
            )
        )

        if proc.returncode == 0:
            mp4_part.replace(mp4)
