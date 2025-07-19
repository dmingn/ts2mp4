import io
import logging
import subprocess
import sys

import logzero
import pytest

from ts2mp4.command import execute_command


def test_execute_command_success() -> None:
    """Test that execute_command runs a command successfully."""
    result = execute_command(["echo", "hello"])
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""
    assert result.returncode == 0


def test_execute_command_failure() -> None:
    """Test that execute_command raises CalledProcessError on failure."""
    with pytest.raises(subprocess.CalledProcessError) as e:
        execute_command(["false"])
    assert e.value.returncode == 1


def test_handles_non_utf8_output() -> None:
    """Test that execute_command handles non-UTF-8 output correctly."""
    # This command prints a non-UTF-8 byte to stderr.
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.buffer.write(b'\\xff'); sys.exit(1)",
    ]
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logzero.logger.addHandler(handler)

    with pytest.raises(subprocess.CalledProcessError):
        execute_command(command)

    logzero.logger.removeHandler(handler)
    log_contents = log_stream.getvalue()
    assert "�" in log_contents


def test_logs_on_success() -> None:
    """Test that execute_command logs stdout and stderr on success."""
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('success stdout'); sys.stderr.write('success stderr')",
    ]
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logzero.logger.addHandler(handler)

    execute_command(command)

    logzero.logger.removeHandler(handler)
    log_contents = log_stream.getvalue()
    assert "success stdout" in log_contents
    assert "success stderr" in log_contents


def test_logs_on_failure() -> None:
    """Test that execute_command logs stdout and stderr on failure."""
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('some stdout'); sys.stderr.write('some stderr'); sys.exit(1)",
    ]
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logzero.logger.addHandler(handler)

    with pytest.raises(subprocess.CalledProcessError):
        execute_command(command)

    logzero.logger.removeHandler(handler)
    log_contents = log_stream.getvalue()
    assert "some stdout" in log_contents
    assert "some stderr" in log_contents
