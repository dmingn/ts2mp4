"""Unit tests for the VideoFile module."""

from pathlib import Path
from types import MappingProxyType
from typing import Callable

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
def mock_get_media_info_func(mocker: MockerFixture) -> MockerFixture:
    """Mock the get_media_info function."""
    return mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(
            streams=(
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1, channels=2),
                Stream(codec_type="audio", index=2, channels=0),
                Stream(codec_type="audio", index=3, channels=6),
                Stream(codec_type="subtitle", index=4),
            )
        ),
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
def test_videofile_properties(
    mock_get_media_info_func: MockerFixture, tmp_path: Path
) -> None:
    """Test that the properties of VideoFile return correct streams."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    video_file = VideoFile(path=dummy_file)

    assert len(video_file.video_streams) == 1
    assert video_file.video_streams[0].codec_type == "video"

    assert len(video_file.audio_streams) == 3
    assert all(s.codec_type == "audio" for s in video_file.audio_streams)

    assert len(video_file.valid_audio_streams) == 2
    for stream in video_file.valid_audio_streams:
        assert stream.channels is not None
        assert stream.channels > 0


@pytest.mark.unit
def test_get_stream_by_index(
    mock_get_media_info_func: MockerFixture, tmp_path: Path
) -> None:
    """Test that get_stream_by_index returns the correct stream."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    video_file = VideoFile(path=dummy_file)

    stream = video_file.get_stream_by_index(3)
    assert stream.index == 3

    with pytest.raises(ValueError):
        video_file.get_stream_by_index(99)


@pytest.mark.unit
def test_converted_video_file_immutable_stream_sources(
    video_file_factory: Callable[..., VideoFile],
) -> None:
    """Test that the stream_sources field is immutable."""
    source_file = video_file_factory()
    stream_sources = {
        0: StreamSource(
            source_video_file=source_file,
            source_stream_index=0,
            conversion_type=ConversionType.CONVERTED,
        )
    }
    converted_file = ConvertedVideoFile(
        path=source_file.path, stream_sources=stream_sources
    )

    assert isinstance(converted_file.stream_sources, MappingProxyType)
    with pytest.raises(TypeError):
        converted_file.stream_sources[1] = "test"  # type: ignore
