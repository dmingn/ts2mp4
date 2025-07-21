"""A tool for converting TS video files to MP4 format."""

import importlib.metadata


def _get_ts2mp4_version() -> str:
    try:
        return importlib.metadata.version("ts2mp4")
    except importlib.metadata.PackageNotFoundError:
        return "Unknown"
