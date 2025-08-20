"""Unit tests for the ts2mp4 module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import StreamSourcesForAudioReEncoding
from ts2mp4.media_info import AudioStream, MediaInfo, VideoStream
from ts2mp4.ts2mp4 import ts2mp4
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)


@pytest.fixture
def mock_video_file(mocker: MockerFixture, tmp_path: Path) -> VideoFile:
    """Mock VideoFile object for ts2mp4 tests."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()

    video_stream = VideoStream(codec_type="video", index=0)
    audio_streams = (
        AudioStream(codec_type="audio", index=1, channels=2),
        AudioStream(codec_type="audio", index=2, channels=6),
    )
    media_info = MediaInfo(streams=(video_stream,) + audio_streams)
    mocker.patch("ts2mp4.video_file.get_media_info", return_value=media_info)

    return VideoFile(path=dummy_file)


@pytest.mark.unit
def test_ts2mp4_orchestrates_calls(
    mock_video_file: MagicMock,
    mocker: MockerFixture,
) -> None:
    """Test that ts2mp4 calls its dependencies correctly."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=ConvertedVideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mock_output_video_file_instance.stream_with_sources = []

    mock_perform_initial_conversion = mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        return_value=mock_output_video_file_instance,
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_perform_initial_conversion.assert_called_once_with(
        mock_video_file, output_file, crf, preset
    )
    assert mock_verify_copied_streams.call_count == 2


@pytest.mark.unit
def test_calls_verify_streams_on_success(
    mock_video_file: MagicMock, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that verify_streams is called on successful conversion."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=ConvertedVideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mock_output_video_file_instance.stream_with_sources = []
    mock_perform_initial_conversion = mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        return_value=mock_output_video_file_instance,
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act
    ts2mp4(mock_video_file, output_file, crf, preset)

    # Assert
    mock_perform_initial_conversion.assert_called_once_with(
        mock_video_file, output_file, crf, preset
    )
    assert mock_verify_copied_streams.call_count == 2


@pytest.mark.unit
def test_ts2mp4_raises_runtime_error_on_ffmpeg_failure(
    mock_video_file: MagicMock, mocker: MockerFixture
) -> None:
    """Test that a RuntimeError is raised on ffmpeg failure."""
    # Arrange
    output_file = Path("output.mp4")
    crf = 23
    preset = "medium"

    mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
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

    mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        side_effect=RuntimeError("ffmpeg failed with return code 1"),
    )
    mock_verify_copied_streams = mocker.patch("ts2mp4.ts2mp4.verify_copied_streams")

    # Act & Assert
    with pytest.raises(RuntimeError):
        ts2mp4(mock_video_file, output_file, crf, preset)

    mock_verify_copied_streams.assert_not_called()


@pytest.mark.unit
def test_ts2mp4_re_encodes_on_stream_integrity_failure(
    mock_video_file: MagicMock, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that re-encoding is triggered on stream integrity failure."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=ConvertedVideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = mocker.MagicMock(spec=MediaInfo)
    mock_output_video_file_instance.media_info.streams = [
        VideoStream(codec_type="video", index=0),
        AudioStream(codec_type="audio", index=1),
        AudioStream(codec_type="audio", index=2),
    ]
    mock_output_video_file_instance.stream_with_sources = []
    mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        return_value=mock_output_video_file_instance,
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_copied_streams",
        side_effect=RuntimeError("Audio stream integrity check failed"),
    )

    mock_re_encoded_file = mocker.MagicMock()
    mock_re_encoded_file.stream_sources = StreamSourcesForAudioReEncoding(
        StreamSources(
            [
                StreamSource(
                    source_video_file=mock_output_video_file_instance,
                    source_stream_index=0,
                    conversion_type=ConversionType.COPIED,
                ),
                StreamSource(
                    source_video_file=mock_video_file,
                    source_stream_index=1,
                    conversion_type=ConversionType.CONVERTED,
                ),
                StreamSource(
                    source_video_file=mock_output_video_file_instance,
                    source_stream_index=2,
                    conversion_type=ConversionType.COPIED,
                ),
            ]
        )
    )

    mock_re_encode = mocker.patch(
        "ts2mp4.ts2mp4.re_encode_mismatched_audio_streams",
        return_value=mock_re_encoded_file,
    )
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
    mock_video_file: MagicMock, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that a RuntimeError is raised on re-encode failure."""
    # Arrange
    output_file = tmp_path / "output.mp4"
    output_file.touch()
    crf = 23
    preset = "medium"

    mock_output_video_file_instance = mocker.MagicMock(spec=VideoFile)
    mock_output_video_file_instance.path = output_file
    mock_output_video_file_instance.media_info = MagicMock()
    mocker.patch(
        "ts2mp4.ts2mp4.perform_initial_conversion",
        return_value=mock_output_video_file_instance,
    )
    mocker.patch(
        "ts2mp4.ts2mp4.verify_copied_streams",
        side_effect=RuntimeError("Audio stream integrity check failed"),
    )
    mocker.patch(
        "ts2mp4.ts2mp4.re_encode_mismatched_audio_streams",
        side_effect=RuntimeError("Re-encode failed"),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Re-encode failed"):
        ts2mp4(mock_video_file, output_file, crf, preset)
