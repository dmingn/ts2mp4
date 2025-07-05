import subprocess


def test_ts2mp4_help():
    """Test that `ts2mp4 --help` runs without error."""
    result = subprocess.run(
        ["poetry", "run", "ts2mp4", "--help"], capture_output=True, text=True
    )

    # Check that the command exits successfully.
    assert result.returncode == 0
    # Check that the output contains the usage string to ensure the Typer CLI is running.
    assert "Usage:" in result.stdout


def test_python_m_ts2mp4_help():
    """Test that `python -m ts2mp4 --help` runs without error."""
    result = subprocess.run(
        ["poetry", "run", "python", "-m", "ts2mp4", "--help"],
        capture_output=True,
        text=True,
    )

    # Check that the command exits successfully.
    assert result.returncode == 0
    # Check that the output contains the usage string to ensure the Typer CLI is running.
    assert "Usage:" in result.stdout
