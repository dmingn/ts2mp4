import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ts2mp4 import ts2mp4


def test_calls_ffmpeg_with_correct_args(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_subprocess_run = mocker.patch("subprocess.run")
    mocker.patch("ts2mp4.ts2mp4.verify_audio_stream_integrity")

    mock_subprocess_run.return_value = MagicMock(
        stdout="ffmpeg stdout", stderr="ffmpeg stderr"
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    expected_command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(input_file),
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-map",
        "0:s?",
        "-f",
        "mp4",
        "-vsync",
        "1",
        "-vf",
        "bwdif",
        "-codec:v",
        "libx265",
        "-crf",
        str(crf),
        "-preset",
        preset,
        "-codec:a",
        "copy",
        "-codec:s",
        "mov_text",
        "-bsf:a",
        "aac_adtstoasc",
        str(output_file),
    ]
    mock_subprocess_run.assert_called_once_with(
        args=expected_command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_calls_verify_audio_stream_integrity_on_success(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("subprocess.run")
    mock_verify_audio_stream_integrity = mocker.patch(
        "ts2mp4.ts2mp4.verify_audio_stream_integrity"
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_verify_audio_stream_integrity.assert_called_once_with(
        input_file=input_file, output_file=output_file
    )


def test_handles_non_utf8_ffmpeg_output(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_subprocess_run = mocker.patch("subprocess.run")
    mocker.patch("ts2mp4.ts2mp4.verify_audio_stream_integrity")

    # Simulate ffmpeg output with invalid UTF-8 bytes
    non_utf8_stderr = b"ffmpeg stderr with invalid byte: \xc6"
    mock_subprocess_run.return_value = MagicMock(
        stdout="ffmpeg stdout", stderr=non_utf8_stderr.decode("utf-8", errors="replace")
    )

    # Act & Assert
    try:
        ts2mp4(input_file, output_file, crf, preset)
    except UnicodeDecodeError:
        pytest.fail("ts2mp4 should not raise UnicodeDecodeError")


def test_raises_called_process_error_on_ffmpeg_failure(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.verify_audio_stream_integrity")
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd="ffmpeg"
    )

    # Act & Assert
    with pytest.raises(subprocess.CalledProcessError):
        ts2mp4(input_file, output_file, crf, preset)


def test_does_not_call_verify_audio_stream_integrity_on_ffmpeg_failure(
    mocker: MockerFixture,
) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_verify_audio_stream_integrity = mocker.patch(
        "ts2mp4.ts2mp4.verify_audio_stream_integrity"
    )
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd="ffmpeg"
    )

    # Act & Assert
    with pytest.raises(subprocess.CalledProcessError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_verify_audio_stream_integrity.assert_not_called()


def test_logs_error_on_ffmpeg_failure(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.verify_audio_stream_integrity")
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_logger_error = mocker.patch("ts2mp4.ts2mp4.logger.error")
    mock_logger_info = mocker.patch("ts2mp4.ts2mp4.logger.info")

    error = subprocess.CalledProcessError(
        returncode=1, cmd="ffmpeg", stderr="ffmpeg error"
    )
    error.stdout = "ffmpeg stdout"
    mock_subprocess_run.side_effect = error

    # Act & Assert
    with pytest.raises(subprocess.CalledProcessError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_logger_error.assert_any_call("FFmpeg failed to execute.")
    mock_logger_info.assert_any_call("FFmpeg Stdout:\nffmpeg stdout")
    mock_logger_info.assert_any_call("FFmpeg Stderr:\nffmpeg error")
