"""End-to-end tests for the ts2mp4 package."""

import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

from ts2mp4.audio_channels import get_frame_channel_counts
from ts2mp4.video_file import AudioStream, VideoFile


@pytest.fixture(autouse=True)
def cleanup_files(
    mp4_file: Path, mixed_surround_mp4_file: Path
) -> Generator[None, None, None]:
    """Ensure the .mp4 and .log files are removed before and after each test."""

    def _cleanup() -> None:
        for output_file in (mp4_file, mixed_surround_mp4_file):
            output_file.unlink(missing_ok=True)
            for log_file in output_file.parent.glob("*.log"):
                if log_file.stem.startswith(f"{output_file.stem}-"):
                    log_file.unlink(missing_ok=True)

    _cleanup()
    yield
    _cleanup()


@pytest.mark.e2e
def test_ts2mp4_conversion_success(
    ts_file: Path, mp4_file: Path, project_root: Path
) -> None:
    """Test successful conversion of a .ts file to .mp4."""
    command = ["uv", "run", "ts2mp4", str(ts_file)]
    subprocess.run(command, capture_output=True, cwd=project_root, check=True)

    assert mp4_file.exists()
    assert mp4_file.stat().st_size > 0


@pytest.mark.e2e
def test_ts2mp4_encodes_mixed_surround_audio_as_fixed_5_1(
    mixed_surround_ts_file: Path, mixed_surround_mp4_file: Path, project_root: Path
) -> None:
    """Audio that switches from stereo to 5.1ch is 5.1ch in every output frame."""
    # Arrange
    command = ["uv", "run", "ts2mp4", str(mixed_surround_ts_file)]

    # Act
    subprocess.run(command, capture_output=True, cwd=project_root, check=True)

    # Assert
    output_audio_stream = AudioStream(
        file=VideoFile(path=mixed_surround_mp4_file), index=1
    )
    assert get_frame_channel_counts(output_audio_stream) == frozenset({6})


@pytest.mark.e2e
def test_ts2mp4_file_not_found_error(mp4_file: Path, project_root: Path) -> None:
    """Test error handling when the input .ts file does not exist."""
    non_existent_file = project_root / "non_existent.ts"
    command = ["uv", "run", "ts2mp4", str(non_existent_file)]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=project_root, check=True)
    assert not mp4_file.exists()


@pytest.mark.e2e
def test_ts2mp4_no_input_file_error(mp4_file: Path, project_root: Path) -> None:
    """Test error handling when no input file is provided."""
    command = ["uv", "run", "ts2mp4"]
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command, capture_output=True, cwd=project_root, check=True)
    assert not mp4_file.exists()
