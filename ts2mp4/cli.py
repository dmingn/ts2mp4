from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ts2mp4.ts2mp4 import ts2mp4


@dataclass(frozen=True)
class Job:
    ts: Path
    ss: Optional[str]
    to: Optional[str]


async def worker(queue: asyncio.Queue[Job]):
    while True:
        job = await queue.get()

        await ts2mp4(ts=job.ts, ss=job.ss, to=job.to)

        queue.task_done()


async def parent(path: Path, n_worker: int, ss: Optional[str], to: Optional[str]):
    queue: asyncio.Queue[Job] = asyncio.Queue()

    if path.is_dir():
        for ts in path.glob("*.ts"):
            await queue.put(Job(ts=ts, ss=ss, to=to))
    elif path.suffix == ".ts":
        await queue.put(Job(ts=path, ss=ss, to=to))

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
    parser.add_argument("-n", "--n_worker", type=int, default=1)
    parser.add_argument("-ss", type=str, default=None)
    parser.add_argument("-to", type=str, default=None)
    args = parser.parse_args()

    asyncio.run(parent(**vars(args)))
