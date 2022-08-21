import argparse
from pathlib import Path

from ts2mp4.ts2mp4 import ts2mp4


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("-ss", type=str, default=None)
    parser.add_argument("-to", type=str, default=None)
    args = parser.parse_args()

    ts2mp4(ts=args.path, ss=args.ss, to=args.to)
