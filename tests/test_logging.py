import subprocess
from pathlib import Path

import pytest


@pytest.mark.e2e
def test_log_file_creation_and_content(tmp_path: Path, project_root: Path) -> None:
    """Test that a log file is created and contains expected messages."""

    # Define paths directly using tmp_path
    temp_ts_file = tmp_path / "dummy.ts"
    temp_log_file = tmp_path / "conversion.log"

    # Create the dummy .ts file
    temp_ts_file.write_bytes(b"This is a dummy ts file content.")

    command = [
        "poetry",
        "run",
        "ts2mp4",
        str(temp_ts_file),
        "--log-file",
        str(temp_log_file),
    ]

    # Run the command without check=True to prevent CalledProcessError on ffmpeg failure
    subprocess.run(command, capture_output=True, cwd=project_root, check=False)

    assert temp_log_file.exists()
    log_content = temp_log_file.read_text()

    # Assert that the log file contains some expected content from ts2mp4
    assert "Conversion Log" in log_content
