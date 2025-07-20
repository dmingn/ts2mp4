import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def cleanup_files(mp4_file: Path) -> Generator[None, None, None]:
    """Ensures the .mp4 and .log files are removed before and after each test."""

    def _cleanup() -> None:
        mp4_file.unlink(missing_ok=True)
        for log_file in mp4_file.parent.glob(f"{mp4_file.stem}*.log"):
            log_file.unlink(missing_ok=True)

    _cleanup()
    yield
    _cleanup()


def test_ts2mp4_conversion_success(
    ts_file: Path, mp4_file: Path, project_root: Path
) -> None:
    """Test successful conversion of a .ts file to .mp4."""
    command = ["poetry", "run", "ts2mp4", str(ts_file)]
    subprocess.run(command, capture_output=True, cwd=project_root, check=True)

    assert mp4_file.exists()
    assert mp4_file.stat().st_size > 0


def test_ts2mp4_file_not_found_error(mp4_file: Path, project_root: Path) -> None:
    """Test error handling when the input .ts file does not exist."""
    non_existent_file = project_root / "non_existent.ts"
    command = ["poetry", "run", "ts2mp4", str(non_existent_file)]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=project_root, check=True)
    assert not mp4_file.exists()


def test_ts2mp4_no_input_file_error(mp4_file: Path, project_root: Path) -> None:
    """Test error handling when no input file is provided."""
    command = ["poetry", "run", "ts2mp4"]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=project_root, check=True)
    assert not mp4_file.exists()
