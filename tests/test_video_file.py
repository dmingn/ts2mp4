"""Unit tests for the VideoFile module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.fixture
def mock_get_media_info_func(mocker: MockerFixture) -> MagicMock:
    """Mock the get_media_info function."""
    return mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(
            streams=(
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1, channels=2),
                Stream(codec_type="audio", index=2, channels=0),  # Invalid audio stream
                Stream(codec_type="audio", index=3, channels=6),
                Stream(codec_type="subtitle", index=4),
            )
        ),
    )


@pytest.fixture
def dummy_video_file(tmp_path: Path) -> VideoFile:
    """Create a dummy VideoFile instance."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.fixture
def stream_source(dummy_video_file: VideoFile) -> StreamSource:
    """Create a dummy StreamSource instance."""
    return StreamSource(
        source_video_file=dummy_video_file,
        source_stream_index=0,
        conversion_type=ConversionType.COPIED,
    )


@pytest.mark.unit
def test_videofile_instantiation_success(tmp_path: Path) -> None:
    """Test that VideoFile can be instantiated with a valid path."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    video_file = VideoFile(path=dummy_file)
    assert video_file.path == dummy_file


@pytest.mark.unit
def test_videofile_instantiation_non_existent_file_raises_error(tmp_path: Path) -> None:
    """Test that instantiating VideoFile with a non-existent file raises ValidationError."""
    non_existent_file = tmp_path / "non_existent.ts"
    with pytest.raises(ValidationError):
        VideoFile(path=non_existent_file)


@pytest.mark.unit
def test_videofile_media_info_property(
    mock_get_media_info_func: MagicMock, dummy_video_file: VideoFile
) -> None:
    """Test that the media_info property calls get_media_info and returns the correct object."""
    media_info = dummy_video_file.media_info

    mock_get_media_info_func.assert_called_once_with(dummy_video_file.path)
    assert isinstance(media_info, MediaInfo)
    assert len(media_info.streams) == 5


@pytest.mark.unit
def test_videofile_audio_streams_property(
    mock_get_media_info_func: MagicMock, dummy_video_file: VideoFile
) -> None:
    """Test that the audio_streams property returns only audio streams."""
    audio_streams = dummy_video_file.audio_streams

    assert len(audio_streams) == 3  # The mock contains 3 audio streams
    for stream in audio_streams:
        assert stream.codec_type == "audio"


@pytest.mark.unit
def test_videofile_valid_audio_streams_property(
    mock_get_media_info_func: MagicMock, dummy_video_file: VideoFile
) -> None:
    """Test that the valid_audio_streams property returns only valid audio streams."""
    valid_audio_streams = dummy_video_file.valid_audio_streams

    assert len(valid_audio_streams) == 2  # Only streams with channels > 0
    for stream in valid_audio_streams:
        assert stream.codec_type == "audio"
        assert stream.channels is not None and stream.channels > 0


@pytest.mark.unit
def test_stream_source_instantiation(dummy_video_file: VideoFile) -> None:
    """Test that StreamSource can be instantiated with valid data."""
    stream_source = StreamSource(
        source_video_file=dummy_video_file,
        source_stream_index=0,
        conversion_type=ConversionType.COPIED,
    )
    assert stream_source.source_video_file == dummy_video_file
    assert stream_source.source_stream_index == 0
    assert stream_source.conversion_type == ConversionType.COPIED


@pytest.mark.unit
def test_stream_source_instantiation_with_invalid_index(
    dummy_video_file: VideoFile,
) -> None:
    """Test that StreamSource raises ValidationError for a negative stream index."""
    with pytest.raises(ValidationError):
        StreamSource(
            source_video_file=dummy_video_file,
            source_stream_index=-1,
            conversion_type=ConversionType.COPIED,
        )


@pytest.mark.unit
def test_converted_video_file_instantiation(
    dummy_video_file: VideoFile, stream_source: StreamSource
) -> None:
    """Test that ConvertedVideoFile can be instantiated with valid data."""
    converted_file = ConvertedVideoFile(
        path=dummy_video_file.path,
        stream_sources=(stream_source,),
    )
    assert converted_file.path == dummy_video_file.path
    assert converted_file.stream_sources == (stream_source,)
