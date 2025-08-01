"""Unit tests for the ts2mp4 module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.ts2mp4 import ts2mp4


@pytest.fixture
def mock_get_media_info(mocker: MockerFixture) -> MagicMock:
    """Mock get_media_info to return a standard MediaInfo object."""
    mock = mocker.patch("ts2mp4.ts2mp4.get_media_info")
    mock.return_value = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1, channels=2),
            Stream(codec_type="audio", index=2, channels=0),  # Invalid stream
            Stream(codec_type="audio", index=3, channels=6),
        )
    )
    return mock


@pytest.mark.unit
def test_calls_execute_ffmpeg_with_correct_args(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that ts2mp4 calls execute_ffmpeg with the correct arguments."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch("ts2mp4.ts2mp4.verify_streams")

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
        "0:1",
        "-map",
        "0:3",
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
    mock_execute_ffmpeg.assert_called_once_with(expected_args)
    mock_get_media_info.assert_called_once_with(input_file)


@pytest.mark.unit
def test_calls_verify_streams_on_success(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that verify_streams is called on successful conversion."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_verify_streams.assert_called_once_with(
        input_file=input_file, output_file=output_file, stream_type="audio"
    )
    mock_get_media_info.assert_called_once_with(input_file)


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that a RuntimeError is raised on ffmpeg failure."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(input_file, output_file, crf, preset)
    mock_get_media_info.assert_called_once_with(input_file)


@pytest.mark.unit
def test_does_not_call_verify_streams_on_ffmpeg_failure(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that ts2mp4 does not call verify_streams on failure."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(input_file, output_file, crf, preset)

    mock_verify_streams.assert_not_called()
    mock_get_media_info.assert_called_once_with(input_file)


@pytest.mark.unit
def test_ts2mp4_re_encodes_on_stream_integrity_failure(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that re-encoding is triggered on stream integrity failure."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg",
        return_value=FFmpegResult(stdout=b"", stderr="", returncode=0),
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_streams",
        side_effect=RuntimeError("Audio stream integrity check failed"),
    )
    mock_re_encode = mocker.patch("ts2mp4.ts2mp4.re_encode_mismatched_audio_streams")
    mocker.patch("pathlib.Path.replace")

    # Act
    ts2mp4(input_file, output_file, crf, preset)

    # Assert
    mock_re_encode.assert_called_once_with(
        original_file=input_file,
        encoded_file=output_file,
        output_file=output_file.with_suffix(output_file.suffix + ".temp"),
    )
    mock_get_media_info.assert_called_once_with(input_file)


@pytest.mark.unit
def test_ts2mp4_re_encode_failure_raises_error(
    mocker: MockerFixture, mock_get_media_info: MagicMock
) -> None:
    """Test that a RuntimeError is raised on re-encode failure."""
    # Arrange
    input_file = Path("input.ts")
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.execute_ffmpeg",
        return_value=FFmpegResult(stdout=b"", stderr="", returncode=0),
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_streams",
        side_effect=RuntimeError("Audio stream integrity check failed"),
    )
    mocker.patch(
        "ts2mp4.ts2mp4.re_encode_mismatched_audio_streams",
        side_effect=RuntimeError("Re-encode failed"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Re-encode failed"):
        ts2mp4(input_file, output_file, crf, preset)
    mock_get_media_info.assert_called_once_with(input_file)
