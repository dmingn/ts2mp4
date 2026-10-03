"""Unit tests for the ts2mp4 module."""

from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.stream_integrity import IntegrityReport
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import VideoFile

_OK_REPORT = IntegrityReport(mismatched_output_indices=frozenset())
_MISMATCH_REPORT = IntegrityReport(mismatched_output_indices=frozenset({1}))
_FFMPEG_RUNNER = FakeFFmpegRunner()


@pytest.mark.unit
def test_ts2mp4_builds_video_file_conversion_plan_with_given_parameters(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Pass the input file, crf, and preset to the video file conversion plan builder."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_build_video_file_conversion_plan = mocker.patch(
        "ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding"
    )
    mocker.patch("ts2mp4.ts2mp4.execute_conversion")
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT)

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)

    # Assert
    mock_build_video_file_conversion_plan.assert_called_once_with(
        mock_video_file, crf=crf, preset=preset
    )


@pytest.mark.unit
def test_ts2mp4_converts_video_file_conversion_plan_to_output(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Convert the video file conversion plan into the output path."""
    # Arrange
    output_file = Path("output.mp4")

    mock_build_video_file_conversion_plan = mocker.patch(
        "ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding"
    )
    mock_execute_conversion = mocker.patch("ts2mp4.ts2mp4.execute_conversion")
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT)

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    mock_execute_conversion.assert_called_once_with(
        mock_build_video_file_conversion_plan.return_value, output_file, _FFMPEG_RUNNER
    )


@pytest.mark.unit
def test_ts2mp4_checks_integrity_of_video_encoded_file(
    mock_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """Check integrity of the file produced by the video conversion."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")
    mocker.patch(
        "ts2mp4.ts2mp4.execute_conversion",
        return_value=mock_output_video_file_instance,
    )
    mock_check_integrity = mocker.patch(
        "ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT
    )

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)

    # Assert
    mock_check_integrity.assert_called_once_with(
        mock_output_video_file_instance, _FFMPEG_RUNNER
    )


@pytest.mark.unit
def test_ts2mp4_skips_audio_encoding_when_integrity_is_ok(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Do not encode audio when the integrity report has no mismatch."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")
    mock_execute_conversion = mocker.patch("ts2mp4.ts2mp4.execute_conversion")
    mocker.patch("ts2mp4.ts2mp4.check_integrity", return_value=_OK_REPORT)
    mock_build_audio_file_conversion_plan = mocker.patch(
        "ts2mp4.ts2mp4.build_file_conversion_plan_for_audio_encoding"
    )

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)

    # Assert
    mock_build_audio_file_conversion_plan.assert_not_called()
    mock_execute_conversion.assert_called_once()


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Propagate RuntimeError when the video conversion fails."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")
    mocker.patch(
        "ts2mp4.ts2mp4.execute_conversion",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="ffmpeg failed with return code 1"):
        ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)


@pytest.mark.unit
def test_ts2mp4_does_not_check_integrity_on_ffmpeg_failure(
    mock_video_file: VideoFile, mocker: MockerFixture
) -> None:
    """Skip check_integrity when the video conversion raises."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")
    mocker.patch(
        "ts2mp4.ts2mp4.execute_conversion",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )
    mock_check_integrity = mocker.patch("ts2mp4.ts2mp4.check_integrity")

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)

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

    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")
    mocker.patch("ts2mp4.ts2mp4.execute_conversion")
    mocker.patch(
        "ts2mp4.ts2mp4.check_integrity",
        side_effect=RuntimeError("Stream type mismatch for stream index 1"),
    )
    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_audio_encoding")

    # Act & Assert
    with pytest.raises(RuntimeError, match="Stream type mismatch"):
        ts2mp4(mock_video_file, output_file, crf, preset, _FFMPEG_RUNNER)


class _AudioFallbackMocks(NamedTuple):
    video_encoded_file: MagicMock
    audio_encoded_file: MagicMock
    check_integrity: MagicMock
    build_audio_file_conversion_plan: MagicMock
    execute_conversion: MagicMock
    check_audio_quality: MagicMock
    replace: MagicMock


@pytest.fixture
def audio_fallback_mocks(mocker: MockerFixture) -> _AudioFallbackMocks:
    """Patch collaborators so ts2mp4 re-encodes audio and the result passes."""
    video_encoded_file = mocker.MagicMock(spec=VideoFile)
    video_encoded_file.path = Path("output.mp4")
    audio_encoded_file = mocker.MagicMock(spec=VideoFile)
    audio_encoded_file.path = Path("output.mp4.temp")
    mocker.patch("ts2mp4.ts2mp4.build_file_conversion_plan_for_video_encoding")

    return _AudioFallbackMocks(
        video_encoded_file=video_encoded_file,
        audio_encoded_file=audio_encoded_file,
        check_integrity=mocker.patch(
            "ts2mp4.ts2mp4.check_integrity",
            side_effect=[_MISMATCH_REPORT, _OK_REPORT],
        ),
        build_audio_file_conversion_plan=mocker.patch(
            "ts2mp4.ts2mp4.build_file_conversion_plan_for_audio_encoding"
        ),
        execute_conversion=mocker.patch(
            "ts2mp4.ts2mp4.execute_conversion",
            side_effect=[video_encoded_file, audio_encoded_file],
        ),
        check_audio_quality=mocker.patch(
            "ts2mp4.ts2mp4.check_audio_quality", return_value={}
        ),
        replace=mocker.patch("pathlib.Path.replace"),
    )


@pytest.mark.unit
def test_ts2mp4_builds_audio_file_conversion_plan_on_integrity_failure(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Build the audio file conversion plan from the report when the integrity check fails."""
    # Arrange
    output_file = Path("output.mp4")

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    audio_fallback_mocks.build_audio_file_conversion_plan.assert_called_once_with(
        original_file=mock_video_file,
        encoded_file=audio_fallback_mocks.video_encoded_file,
        integrity_report=_MISMATCH_REPORT,
        libfdk_aac_available=False,
    )


@pytest.mark.unit
def test_ts2mp4_converts_audio_file_conversion_plan_to_temp_file(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Convert the audio file conversion plan into a temp file next to the output."""
    # Arrange
    output_file = Path("output.mp4")

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    audio_fallback_mocks.execute_conversion.assert_called_with(
        audio_fallback_mocks.build_audio_file_conversion_plan.return_value,
        Path("output.mp4.temp"),
        _FFMPEG_RUNNER,
    )


@pytest.mark.unit
def test_ts2mp4_checks_integrity_of_audio_encoded_file(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Check integrity of the audio-encoded file after re-encoding audio."""
    # Arrange
    output_file = Path("output.mp4")

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    audio_fallback_mocks.check_integrity.assert_called_with(
        audio_fallback_mocks.audio_encoded_file, _FFMPEG_RUNNER
    )


@pytest.mark.unit
def test_ts2mp4_raises_when_audio_encoded_file_fails_integrity(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Raise RuntimeError when the audio-encoded file still mismatches."""
    # Arrange
    output_file = Path("output.mp4")
    audio_fallback_mocks.check_integrity.side_effect = [
        _MISMATCH_REPORT,
        _MISMATCH_REPORT,
    ]

    # Act & Assert
    with pytest.raises(
        RuntimeError, match="Stream integrity check failed after audio encoding"
    ):
        ts2mp4(
            mock_video_file,
            output_file,
            crf=23,
            preset="medium",
            ffmpeg_runner=_FFMPEG_RUNNER,
        )


@pytest.mark.unit
def test_ts2mp4_checks_audio_quality_of_audio_encoded_file(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Check audio quality of the audio-encoded file."""
    # Arrange
    output_file = Path("output.mp4")

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    audio_fallback_mocks.check_audio_quality.assert_called_once_with(
        audio_fallback_mocks.audio_encoded_file, _FFMPEG_RUNNER
    )


@pytest.mark.unit
def test_ts2mp4_replaces_output_with_audio_encoded_file(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Replace the output path with the temp file holding the re-encoded audio."""
    # Arrange
    output_file = Path("output.mp4")

    # Act
    ts2mp4(
        mock_video_file,
        output_file,
        crf=23,
        preset="medium",
        ffmpeg_runner=_FFMPEG_RUNNER,
    )

    # Assert
    audio_fallback_mocks.replace.assert_called_once_with(output_file)


@pytest.mark.unit
def test_ts2mp4_raises_on_audio_encode_failure(
    mock_video_file: VideoFile, audio_fallback_mocks: _AudioFallbackMocks
) -> None:
    """Propagate RuntimeError when the audio conversion fails."""
    # Arrange
    output_file = Path("output.mp4")
    audio_fallback_mocks.execute_conversion.side_effect = [
        audio_fallback_mocks.video_encoded_file,
        RuntimeError("Encode failed"),
    ]

    # Act & Assert
    with pytest.raises(RuntimeError, match="Encode failed"):
        ts2mp4(
            mock_video_file,
            output_file,
            crf=23,
            preset="medium",
            ffmpeg_runner=_FFMPEG_RUNNER,
        )
