"""Unit tests for the ts2mp4 module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.media_info import Stream
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import VideoFile


@pytest.fixture
def mock_video_file(mocker: MockerFixture) -> Any:
    """Mock VideoFile object for ts2mp4 tests."""
    return mocker.MagicMock(
        autospec=VideoFile,
        path=Path("input.ts"),
        valid_audio_streams=[
            Stream(codec_type="audio", index=1, channels=2),
            Stream(codec_type="audio", index=3, channels=6),
        ],
    )


@pytest.mark.unit
def test_calls_execute_ffmpeg_with_correct_args(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that ts2mp4 calls execute_ffmpeg with the correct arguments."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    # Mock VideoFile constructor to prevent file existence check
    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()  # Add a mock media_info
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mocker.patch("ts2mp4.ts2mp4.verify_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    expected_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(mock_video_file.path),
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


@pytest.mark.unit
def test_calls_verify_streams_on_success(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that verify_streams is called on successful conversion."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(stdout=b"", stderr="", returncode=0)
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_verify_streams.assert_called_once_with(
        input_file=mock_video_file,
        output_file=mock_output_video_file_instance,
        stream_type="audio",
    )


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that a RuntimeError is raised on ffmpeg failure."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

    mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(mock_video_file, output_file, crf, preset)


@pytest.mark.unit
def test_does_not_call_verify_streams_on_ffmpeg_failure(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that ts2mp4 does not call verify_streams on failure."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

    mock_execute_ffmpeg = mocker.patch("ts2mp4.ts2mp4.execute_ffmpeg")
    mock_verify_streams = mocker.patch("ts2mp4.ts2mp4.verify_streams")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(mock_video_file, output_file, crf, preset)

    mock_verify_streams.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_re_encodes_on_stream_integrity_failure(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that re-encoding is triggered on stream integrity failure."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

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
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_re_encode.assert_called_once_with(
        original_file=mock_video_file,
        encoded_file=mock_output_video_file_instance,
        output_file=output_file.with_suffix(output_file.suffix + ".temp"),
    )


@pytest.mark.unit
def test_ts2mp4_re_encode_failure_raises_error(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that a RuntimeError is raised on re-encode failure."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.VideoFile", return_value=mock_output_video_file_instance
    )

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
        ts2mp4(mock_video_file, output_file, crf, preset)
