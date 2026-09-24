"""Unit tests for the stream_integrity module."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_integrity import compare_stream_hashes, verify_copied_streams
from ts2mp4.stream_source import (
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    StreamWithSource,
)
from ts2mp4.video_file import AudioStream, OtherStream, VideoFile, VideoStream


@pytest.fixture
def input_video_file(tmp_path: Path) -> VideoFile:
    """Return an input VideoFile instance."""
    dummy_file = tmp_path / "dummy_input.ts"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.fixture
def output_video_file(tmp_path: Path) -> VideoFile:
    """Return an output VideoFile instance."""
    dummy_file = tmp_path / "dummy_output.mp4.part"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.mark.unit
def test_compare_stream_hashes_returns_true_when_hashes_match(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """compare_stream_hashes returns True when both MD5 hashes match."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash")

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
    )

    # Assert
    assert result is True


@pytest.mark.unit
def test_compare_stream_hashes_returns_false_when_hashes_differ(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """compare_stream_hashes returns False when MD5 hashes differ."""
    # Arrange
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
    )

    # Assert
    assert result is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(RuntimeError("Mock error"), id="runtime_error"),
        pytest.param(
            FFmpegProcessError("ffmpeg failed with exit code 69"),
            id="ffmpeg_process_error",
        ),
    ],
)
def test_compare_stream_hashes_returns_false_when_hashing_fails(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
    error: Exception,
) -> None:
    """compare_stream_hashes returns False when get_stream_md5 raises."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", side_effect=error)

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
    )

    # Assert
    assert result is False


@pytest.fixture
def mock_converted_video_file(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> MagicMock:
    """Return a mocked ConvertedVideoFile instance."""
    mocker.patch(
        "ts2mp4.video_file.probe_file",
        return_value=FFprobeOutput(
            streams=(
                FFprobeStream(index=0, codec_type="video"),
                FFprobeStream(index=1, codec_type="audio"),
            )
        ),
    )
    input_streams = frozenset(
        (
            VideoStream(file=input_video_file, index=0),
            AudioStream(file=input_video_file, index=1),
        )
    )
    output_streams = frozenset(
        (
            VideoStream(file=output_video_file, index=0),
            AudioStream(file=output_video_file, index=1),
        )
    )

    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = output_video_file.path
    mock_converted_file.streams = output_streams
    mock_converted_file.stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=next(s for s in input_streams if s.index == 0),
                conversion_type="encoded",
            ),
            StreamSource(
                source_stream=next(s for s in input_streams if s.index == 1),
                conversion_type="copied",
            ),
        )
    )

    # MagicMock doesn't automatically handle properties that are generators
    type(mock_converted_file).stream_with_sources = mocker.PropertyMock(
        return_value=[
            StreamWithSource(
                stream=next(s for s in output_streams if s.index == i),
                source=source,
            )
            for i, source in enumerate(mock_converted_file.stream_sources)
        ]
    )

    return mock_converted_file


@pytest.mark.unit
def test_verify_copied_streams_passes_when_hashes_match(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """verify_copied_streams returns normally when copied stream hashes match."""
    # Arrange
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    # Act
    verify_copied_streams(mock_converted_video_file)

    # Assert
    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_copied_streams_raises_when_hashes_differ(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """verify_copied_streams raises RuntimeError when a copied stream hash mismatches."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)

    # Act & Assert
    with pytest.raises(
        RuntimeError,
        match="Audio stream integrity check failed for stream at index 1",
    ):
        verify_copied_streams(mock_converted_video_file)


@pytest.mark.unit
def test_verify_copied_streams_skips_when_no_copied_streams(
    mocker: MockerFixture, mock_converted_video_file: MagicMock
) -> None:
    """verify_copied_streams does not compare hashes when no streams are copied."""
    # Arrange
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )
    stream_sources = list(mock_converted_video_file.stream_sources)
    stream_sources[1] = StreamSource(
        source_stream=stream_sources[1].source_stream,
        conversion_type="encoded",
    )
    mock_converted_video_file.stream_sources = StreamSources(root=tuple(stream_sources))
    type(mock_converted_video_file).stream_with_sources = mocker.PropertyMock(
        return_value=[
            StreamWithSource(
                stream=next(
                    s for s in mock_converted_video_file.streams if s.index == i
                ),
                source=source,
            )
            for i, source in enumerate(mock_converted_video_file.stream_sources)
        ]
    )

    # Act
    verify_copied_streams(mock_converted_video_file)

    # Assert
    mock_compare_stream_hashes.assert_not_called()


@pytest.mark.unit
def test_verify_copied_streams_raises_for_unsupported_stream_type(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
    output_video_file: VideoFile,
) -> None:
    """verify_copied_streams raises NotImplementedError for non-A/V copied streams."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)
    mock_converted_video_file.streams = frozenset(
        OtherStream(file=output_video_file, index=1) if stream.index == 1 else stream
        for stream in mock_converted_video_file.streams
    )
    type(mock_converted_video_file).stream_with_sources = mocker.PropertyMock(
        return_value=[
            StreamWithSource(
                stream=next(
                    s for s in mock_converted_video_file.streams if s.index == i
                ),
                source=source,
            )
            for i, source in enumerate(mock_converted_video_file.stream_sources)
        ]
    )

    # Act & Assert
    with pytest.raises(
        NotImplementedError,
        match="Stream integrity check for non-audio/video streams is not implemented.",
    ):
        verify_copied_streams(mock_converted_video_file)
