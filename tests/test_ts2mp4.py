import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ts2mp4.ts2mp4 import ts2mp4


def test_ts2mp4_successful_conversion(mocker):
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_verify_audio_stream_integrity = mocker.patch(
        "ts2mp4.ts2mp4.verify_audio_stream_integrity"
    )

    mock_subprocess_run.return_value = MagicMock(
        stdout="ffmpeg stdout", stderr="ffmpeg stderr"
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    expected_command = [
        "ffmpeg",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(input_file),
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
        "-bsf:a",
        "aac_adtstoasc",
        str(output_file),
    ]
    mock_subprocess_run.assert_called_once_with(
        args=expected_command, check=True, capture_output=True, text=True
    )
    mock_verify_audio_stream_integrity.assert_called_once_with(
        input_file=input_file, output_file=output_file
    )


def test_ts2mp4_ffmpeg_failure(mocker):
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_verify_audio_stream_integrity = mocker.patch(
        "ts2mp4.ts2mp4.verify_audio_stream_integrity"
    )
    mock_logger_error = mocker.patch("ts2mp4.ts2mp4.logger.error")

    error = subprocess.CalledProcessError(
        returncode=1, cmd="ffmpeg", stderr="ffmpeg error"
    )
    error.stdout = "ffmpeg stdout"
    mock_subprocess_run.side_effect = error

    # Act & Assert
    with pytest.raises(subprocess.CalledProcessError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_verify_audio_stream_integrity.assert_not_called()
    mock_logger_error.assert_any_call("FFmpeg failed to execute.")
    mock_logger_error.assert_any_call("FFmpeg Stdout:\nffmpeg stdout")
    mock_logger_error.assert_any_call("FFmpeg Stderr:\nffmpeg error")
