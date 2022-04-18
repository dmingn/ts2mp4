from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


async def ts2mp4(ts: Path):
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
        )

        await proc.wait()

        if proc.returncode == 0:
            mp4_part.replace(mp4)


async def worker(queue: asyncio.Queue[Path]):
    while True:
        ts = await queue.get()

        await ts2mp4(ts)

        queue.task_done()


async def job(path: Path, n_worker: int):
    queue: asyncio.Queue[Path] = asyncio.Queue()

    if path.is_dir():
        for ts in path.glob("*.ts"):
            await queue.put(ts)
    elif path.suffix == ".ts":
        await queue.put(path)

    tasks = []
    for _ in range(n_worker):
        task = asyncio.create_task(worker(queue))
        tasks.append(task)

    await queue.join()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("-n", "--n_worker", type=int)
    args = parser.parse_args()

    asyncio.run(job(path=args.path, n_worker=args.n_worker))
