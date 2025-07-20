from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.ts2mp4 import ts2mp4


@pytest.mark.unit
def test_calls_execute_ffmpeg_with_correct_args(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch("ts2mp4.ts2mp4.get_mismatched_audio_stream_indices", return_value=[])

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


@pytest.mark.unit
def test_calls_get_mismatched_audio_stream_indices_on_success(
    mocker: MockerFixture,
) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mock_get_mismatched_indices = mocker.patch(
        "ts2mp4.ts2mp4.get_mismatched_audio_stream_indices", return_value=[]
    )

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_get_mismatched_indices.assert_called_once_with(
        input_file=input_file, output_file=output_file
    )


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(mocker: MockerFixture) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.get_mismatched_audio_stream_indices")
    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(input_file, output_file, crf, preset)


@pytest.mark.unit
def test_does_not_call_get_mismatched_indices_on_ffmpeg_failure(
    mocker: MockerFixture,
) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_get_mismatched_indices = mocker.patch(
        "ts2mp4.ts2mp4.get_mismatched_audio_stream_indices"
    )
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_get_mismatched_indices.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_audio_integrity_failure(
    mocker: MockerFixture,
) -> None:
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch(
        "ts2mp4.ts2mp4.get_mismatched_audio_stream_indices", return_value=[0, 2]
    )

    # Act & Assert
    with pytest.raises(
        RuntimeError,
        match="Audio stream integrity check failed for indices: \\[0, 2\\]",
    ):
        ts2mp4(input_file, output_file, crf, preset)
