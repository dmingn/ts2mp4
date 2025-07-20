from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.ts2mp4 import ts2mp4


def test_calls_execute_ffmpeg_with_correct_args(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # Arrange
    input_file = tmp_path / "input.ts"
    output_file = tmp_path / "output.mp4"
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch(
        "ts2mp4.ts2mp4.get_failed_audio_stream_indices_by_integrity_check",
        return_value=[],
    )  # No failed streams

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    expected_args = [
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
    mock_execute_ffmpeg.assert_called_once_with(expected_args)


def test_calls_get_failed_audio_stream_indices_by_integrity_check_on_success(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # Arrange
    input_file = tmp_path / "input.ts"
    output_file = tmp_path / "output.mp4"
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mock_get_failed_audio_stream_indices_by_integrity_check = mocker.patch(
        "ts2mp4.ts2mp4.get_failed_audio_stream_indices_by_integrity_check",
        return_value=[],
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_get_failed_audio_stream_indices_by_integrity_check.assert_called_once_with(
        input_file=input_file, output_file=output_file
    )


def test_ts2mp4_raises_runtime_error_on_failure(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # Arrange
    input_file = tmp_path / "input.ts"
    output_file = tmp_path / "output.mp4"
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.get_failed_audio_stream_indices_by_integrity_check")
    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(input_file, output_file, crf, preset)


def test_does_not_call_get_failed_audio_stream_indices_by_integrity_check_on_failure(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # Arrange
    input_file = tmp_path / "input.ts"
    output_file = tmp_path / "output.mp4"
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_get_failed_audio_stream_indices_by_integrity_check = mocker.patch(
        "ts2mp4.ts2mp4.get_failed_audio_stream_indices_by_integrity_check"
    )
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_get_failed_audio_stream_indices_by_integrity_check.assert_not_called()


def test_calls_audio_repair_on_integrity_failure(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # Arrange
    input_file = tmp_path / "input.ts"
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"
    failed_streams = [0]

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch(
        "ts2mp4.ts2mp4.get_failed_audio_stream_indices_by_integrity_check",
        return_value=failed_streams,
    )
    mock_reencode_and_replace_audio_streams = mocker.patch(
        "ts2mp4.ts2mp4.reencode_and_replace_audio_streams"
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_reencode_and_replace_audio_streams.assert_called_once_with(
        original_ts_file=input_file,
        output_mp4_file=output_file,
        failed_stream_indices=failed_streams,
    )
