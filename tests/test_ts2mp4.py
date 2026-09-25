"""Unit tests for the ts2mp4 module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_integrity import IntegrityReport
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import VideoFile

_OK_REPORT = IntegrityReport(mismatched_output_indices=frozenset())
_MISMATCH_REPORT = IntegrityReport(mismatched_output_indices=frozenset({1}))


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
def test_ts2mp4_encodes_video_with_given_parameters(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Pass the input file, output path, crf, and preset to encode_video_streams."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_encode_video_streams = mocker.patch("ts2mp4.ts2mp4.encode_video_streams")
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT)

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_encode_video_streams.assert_called_once_with(
        mock_video_file, output_file, crf, preset
    )


@pytest.mark.unit
def test_ts2mp4_checks_integrity_of_video_encoded_file(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Check integrity of the file produced by encode_video_streams."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        return_value=mock_output_video_file_instance,
    )
    mock_check_integrity = mocker.patch(
        "ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT
    )

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_check_integrity.assert_called_once_with(mock_output_video_file_instance)


@pytest.mark.unit
def test_ts2mp4_skips_audio_encoding_when_integrity_is_ok(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Do not encode audio when the integrity report has no mismatch."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.encode_video_streams")
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT)
    mock_encode_audio = mocker.patch("ts2mp4.ts2mp4.encode_mismatched_audio_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_encode_audio.assert_not_called()


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
def test_ts2mp4_does_not_check_integrity_on_ffmpeg_failure(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Skip check_integrity when encode_video_streams raises."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.encode_video_streams",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )
    mock_check_integrity = mocker.patch("ts2mp4.ts2mp4.check_integrity")

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(mock_video_file, output_file, crf, preset)

    mock_check_integrity.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_propagates_runtime_error_from_check_integrity(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Propagate unrelated RuntimeErrors instead of falling back to audio encoding."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.encode_video_streams")
    mocker.patch(
        "ts2mp4.ts2mp4.check_integrity",
        side_effect=RuntimeError("Stream type mismatch for stream index 1"),
    )
    mocker.patch("ts2mp4.ts2mp4.encode_mismatched_audio_streams", return_value=None)

    # Act & Assert
    with pytest.raises(RuntimeError, match="Stream type mismatch"):
        ts2mp4(mock_video_file, output_file, crf, preset)


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
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_MISMATCH_REPORT)
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")
    mock_audio_encoded_file = mocker.MagicMock(spec=VideoFile)
    mock_encode_audio = mocker.patch(
        "ts2mp4.ts2mp4.encode_mismatched_audio_streams",
        return_value=mock_audio_encoded_file,
    )
    mock_check_audio_quality = mocker.patch(
        "ts2mp4.ts2mp4.check_audio_quality", return_value={}
    )
    mock_replace = mocker.patch("pathlib.Path.replace")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_verify_copied_streams.assert_called_once_with(mock_audio_encoded_file)
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
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_MISMATCH_REPORT)
    mocker.patch(
        "ts2mp4.ts2mp4.encode_mismatched_audio_streams",
        side_effect=RuntimeError("Encode failed"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Encode failed"):
        ts2mp4(mock_video_file, output_file, crf, preset)
