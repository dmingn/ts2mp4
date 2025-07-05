import subprocess
from pathlib import Path

import pytest

# Define paths relative to the project root
PROJECT_ROOT = Path(__file__).parent.parent
TS_FILE = PROJECT_ROOT / "tests" / "assets" / "test_video.ts"
MP4_FILE = PROJECT_ROOT / "tests" / "assets" / "test_video.mp4"


@pytest.fixture(autouse=True)
def cleanup_mp4_file():
    """Ensures the .mp4 file is removed before and after each test."""
    if MP4_FILE.exists():
        MP4_FILE.unlink()
    yield
    if MP4_FILE.exists():
        MP4_FILE.unlink()


def test_ts2mp4_conversion_success():
    """Test successful conversion of a .ts file to .mp4."""
    command = ["poetry", "run", "ts2mp4", str(TS_FILE)]
    subprocess.run(command, capture_output=True, cwd=PROJECT_ROOT, check=True)

    assert MP4_FILE.exists()
    assert MP4_FILE.stat().st_size > 0


def test_ts2mp4_file_not_found_error():
    """Test error handling when the input .ts file does not exist."""
    non_existent_file = PROJECT_ROOT / "non_existent.ts"
    command = ["poetry", "run", "ts2mp4", str(non_existent_file)]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=PROJECT_ROOT, check=True)
    assert not MP4_FILE.exists()


def test_ts2mp4_no_input_file_error():
    """Test error handling when no input file is provided."""
    command = ["poetry", "run", "ts2mp4"]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=PROJECT_ROOT, check=True)
    assert not MP4_FILE.exists()
