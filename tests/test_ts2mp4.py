"""Unit tests for the ts2mp4 module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import VideoFile


@pytest.fixture
def mock_video_file(mocker: MockerFixture, tmp_path: Path) -> VideoFile:
    """Mock VideoFile object for ts2mp4 tests."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()

    mocker.patch(
        "ts2mp4.video_file.probe_file",
        return_value=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(codec_type="audio", index=1, channels=2),
                FFprobeStream(codec_type="audio", index=2, channels=6),
            )
        ),
    )

    return VideoFile(path=dummy_file)


@pytest.mark.unit
def test_ts2mp4_calls_encode_then_verify_copied_streams(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Call encode_video_streams then verify_copied_streams on success."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file

    mock_encode_video_streams = mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        return_value=mock_output_video_file_instance,
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_encode_video_streams.assert_called_once_with(
        mock_video_file, output_file, crf, preset
    )
    mock_verify_copied_streams.assert_called_once_with(
        converted_file=mock_output_video_file_instance
    )


@pytest.mark.unit
def test_ts2mp4_calls_verify_copied_streams_on_success(
    mock_video_file: VideoFile, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Call verify_copied_streams when conversion succeeds with an existing output."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_encode_video_streams = mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        return_value=mock_output_video_file_instance,
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_encode_video_streams.assert_called_once_with(
        mock_video_file, output_file, crf, preset
    )
    mock_verify_copied_streams.assert_called_once_with(
        converted_file=mock_output_video_file_instance
    )


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Propagate RuntimeError when encode_video_streams fails."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(mock_video_file, output_file, crf, preset)


@pytest.mark.unit
def test_ts2mp4_does_not_call_verify_copied_streams_on_ffmpeg_failure(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Skip verify_copied_streams when encode_video_streams raises."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(mock_video_file, output_file, crf, preset)

    assert mock_verify_copied_streams.call_count == 0


@pytest.mark.unit
def test_ts2mp4_encodes_audio_on_stream_integrity_failure(
    mock_video_file: VideoFile, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Encode mismatched audio and re-verify when stream integrity check fails."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        return_value=mock_output_video_file_instance,
    )
    mock_verify_copied_streams = mocker.patch(
        "ts2mp4.ts2mp4.verify_copied_streams",
        side_effect=[RuntimeError("Audio stream integrity check failed"), None],
    )
    mock_encode_audio = mocker.patch(
        "ts2mp4.ts2mp4.encode_mismatched_audio_streams",
        return_value=mocker.MagicMock(spec=VideoFile),
    )
    mock_check_audio_quality = mocker.patch(
        "ts2mp4.ts2mp4.check_audio_quality", return_value={}
    )
    mock_replace = mocker.patch("pathlib.Path.replace")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    assert mock_verify_copied_streams.call_count == 2
    mock_encode_audio.assert_called_once_with(
        original_file=mock_video_file,
        encoded_file=mock_output_video_file_instance,
        output_file=output_file.with_suffix(output_file.suffix + ".temp"),
    )
    mock_check_audio_quality.assert_called_once()
    mock_replace.assert_called_once()


@pytest.mark.unit
def test_ts2mp4_raises_on_audio_encode_failure(
    mock_video_file: VideoFile, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Propagate RuntimeError when encode_mismatched_audio_streams fails."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        return_value=mock_output_video_file_instance,
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_copied_streams",
        side_effect=RuntimeError("Audio stream integrity check failed"),
    )
    mocker.patch(
        "ts2mp4.ts2mp4.encode_mismatched_audio_streams",
        side_effect=RuntimeError("Encode failed"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Encode failed"):
        ts2mp4(mock_video_file, output_file, crf, preset)
