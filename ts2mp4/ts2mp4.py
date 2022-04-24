from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class _Time:
    _time: datetime.time

    @classmethod
    def from_str(cls, s: str) -> _Time:
        for f in ["%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", "%M:%S", "%S.%f", "%S"]:
            try:
                return cls(_time=datetime.datetime.strptime(s, f).time())
            except ValueError:
                pass

        raise ValueError

    def __sub__(self, other: _Time) -> _Time:
        return _Time(
            _time=datetime.time(
                hour=self._time.hour - other._time.hour,
                minute=self._time.minute - other._time.minute,
                second=self._time.second - other._time.second,
            )
        )

    def __str__(self) -> str:
        return self._time.strftime("%H:%M:%S.%f")


async def ts2mp4(ts: Path, ss: Optional[str], to: Optional[str]):
    ss_ = _Time.from_str(ss) if ss else None
    to_ = _Time.from_str(to) if to else None
    if ss_ and to_:
        to_ -= ss_

    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if not mp4.exists():
        proc = await asyncio.create_subprocess_shell(
            cmd=" ".join(
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

        await proc.wait()

        if proc.returncode == 0:
            mp4_part.replace(mp4)
