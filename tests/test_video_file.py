"""Unit tests for the VideoFile module."""

from pathlib import Path
from typing import Callable

import pytest
from pydantic import ValidationError

from ts2mp4.media_info import Stream
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_videofile_instantiation(tmp_path: Path) -> None:
    """Test VideoFile instantiation."""
    # Test success
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    video_file = VideoFile(path=dummy_file)
    assert video_file.path == dummy_file

    # Test failure with non-existent file
    non_existent_file = tmp_path / "non_existent.ts"
    with pytest.raises(ValidationError):
        VideoFile(path=non_existent_file)


@pytest.mark.unit
def test_videofile_properties(video_file_factory: Callable[..., VideoFile]) -> None:
    """Test the properties of the VideoFile class."""
    streams = [
        Stream(codec_type="video", index=0),
        Stream(codec_type="audio", index=1, channels=2),
        Stream(codec_type="audio", index=2, channels=0),  # Invalid
        Stream(codec_type="audio", index=3, channels=6),
        Stream(codec_type="subtitle", index=4),
    ]
    video_file = video_file_factory(streams=streams)

    # Test video_streams property
    assert len(video_file.video_streams) == 1
    assert video_file.video_streams[0].codec_type == "video"

    # Test audio_streams property
    assert len(video_file.audio_streams) == 3
    assert all(s.codec_type == "audio" for s in video_file.audio_streams)

    # Test valid_audio_streams property
    assert len(video_file.valid_audio_streams) == 2
    for stream in video_file.valid_audio_streams:
        assert stream.channels is not None and stream.channels > 0


@pytest.mark.unit
def test_converted_video_file_instantiation(
    video_file_factory: Callable[..., VideoFile],
) -> None:
    """Test ConvertedVideoFile instantiation."""
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
    assert converted_file.path == source_file.path
    assert converted_file.stream_sources[0].source_stream_index == 0
