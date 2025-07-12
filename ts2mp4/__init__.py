import importlib.metadata


def _get_ts2mp4_version() -> str:
    try:
        return importlib.metadata.version("ts2mp4")
    except importlib.metadata.PackageNotFoundError:
        return "Unknown"
