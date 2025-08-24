"""Unit tests for the VideoFile module."""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from ts2mp4.media_info import AudioStream, MediaInfo, OtherStream, VideoStream
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)


@pytest.fixture
def mock_get_media_info_func(mocker: MockerFixture) -> MagicMock:
    """Mock the get_media_info function."""
    return mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(
            streams=(
                VideoStream(codec_type="video", index=0),
                AudioStream(codec_type="audio", index=1, channels=2),
                AudioStream(
                    codec_type="audio", index=2, channels=0
                ),  # Invalid audio stream
                AudioStream(codec_type="audio", index=3, channels=6),
                OtherStream(codec_type="subtitle", index=4),
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
        source_video_path=dummy_video_file.path,
        source_stream=VideoStream(codec_type="video", index=0),
        conversion_type=ConversionType.COPIED,
    )


@pytest.fixture
def stream_sources(
    dummy_video_file: VideoFile, mocker: MockerFixture, tmp_path: Path
) -> StreamSources:
    """Create a StreamSources instance with mixed stream types."""
    video_file_1 = dummy_video_file
    (tmp_path / "test2.ts").touch()
    video_file_2 = VideoFile(path=(tmp_path / "test2.ts"))

    media_info_1 = MediaInfo(
        streams=(
            VideoStream(codec_type="video", index=0),
            AudioStream(codec_type="audio", index=1, channels=2),
        )
    )
    media_info_2 = MediaInfo(
        streams=(
            VideoStream(codec_type="video", index=0),
            AudioStream(codec_type="audio", index=1, channels=1),
        )
    )

    path_to_media_info = {
        video_file_1.path: media_info_1,
        video_file_2.path: media_info_2,
    }

    def _get_media_info_side_effect(path: Path) -> Optional[MediaInfo]:
        return path_to_media_info.get(path)

    mocker.patch(
        "ts2mp4.video_file.get_media_info", side_effect=_get_media_info_side_effect
    )

    return StreamSources(
        root=(
            StreamSource(
                source_video_path=video_file_1.path,
                source_stream=media_info_1.streams[0],
                conversion_type=ConversionType.CONVERTED,
            ),
            StreamSource(
                source_video_path=video_file_1.path,
                source_stream=media_info_1.streams[1],
                conversion_type=ConversionType.COPIED,
            ),
            StreamSource(
                source_video_path=video_file_2.path,
                source_stream=media_info_2.streams[1],
                conversion_type=ConversionType.COPIED,
            ),
        )
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
def test_videofile_valid_video_streams_property(
    mock_get_media_info_func: MagicMock, dummy_video_file: VideoFile
) -> None:
    """Test that the valid_video_streams property returns only valid video streams."""
    valid_video_streams = dummy_video_file.valid_video_streams

    assert len(valid_video_streams) == 1
    for stream in valid_video_streams:
        assert stream.codec_type == "video"


@pytest.mark.unit
def test_videofile_valid_streams_property(
    mock_get_media_info_func: MagicMock, dummy_video_file: VideoFile
) -> None:
    """Test that the valid_streams property returns all valid streams."""
    valid_streams = dummy_video_file.valid_streams

    assert len(valid_streams) == 3  # 1 valid video + 2 valid audio

    video_stream_count = sum(1 for s in valid_streams if isinstance(s, VideoStream))
    audio_stream_count = sum(1 for s in valid_streams if isinstance(s, AudioStream))

    assert video_stream_count == 1
    assert audio_stream_count == 2


@pytest.mark.unit
def test_stream_source_instantiation(dummy_video_file: VideoFile) -> None:
    """Test that StreamSource can be instantiated with valid data."""
    stream = VideoStream(codec_type="video", index=0)
    stream_source = StreamSource(
        source_video_path=dummy_video_file.path,
        source_stream=stream,
        conversion_type=ConversionType.COPIED,
    )
    assert stream_source.source_video_path == dummy_video_file.path
    assert stream_source.source_stream == stream
    assert stream_source.conversion_type == ConversionType.COPIED


@pytest.mark.unit
def test_converted_video_file_instantiation(
    dummy_video_file: VideoFile, stream_source: StreamSource, mocker: MockerFixture
) -> None:
    """Test that ConvertedVideoFile can be instantiated with valid data."""
    # Mock get_media_info to return a single stream to match the single stream source
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(streams=(stream_source.source_stream,)),
    )

    stream_sources = StreamSources(root=(stream_source,))
    converted_file = ConvertedVideoFile(
        path=dummy_video_file.path,
        stream_sources=stream_sources,
    )
    assert converted_file.path == dummy_video_file.path
    assert converted_file.stream_sources == stream_sources


@pytest.mark.unit
def test_stream_sources_video_stream_sources_property(
    stream_sources: StreamSources,
) -> None:
    """Test that the video_stream_sources property returns only video streams."""
    video_sources = stream_sources.video_stream_sources
    assert len(video_sources) == 1
    assert all(s.source_stream.codec_type == "video" for s in video_sources)


@pytest.mark.unit
def test_stream_sources_audio_stream_sources_property(
    stream_sources: StreamSources,
) -> None:
    """Test that the audio_stream_sources property returns only audio streams."""
    audio_sources = stream_sources.audio_stream_sources
    assert len(audio_sources) == 2
    assert all(s.source_stream.codec_type == "audio" for s in audio_sources)


@pytest.mark.unit
def test_stream_sources_source_video_files_property(
    stream_sources: StreamSources,
) -> None:
    """Test that the source_video_files property returns a set of unique source files."""
    source_files = stream_sources.source_video_files
    assert len(source_files) == 2
    assert all(isinstance(f, VideoFile) for f in source_files)


@pytest.mark.unit
def test_stream_sources_properties_with_empty_sources() -> None:
    """Test that StreamSources properties work correctly with no sources."""
    empty_stream_sources = StreamSources(root=())
    assert len(empty_stream_sources.video_stream_sources) == 0
    assert len(empty_stream_sources.audio_stream_sources) == 0
    assert len(empty_stream_sources.source_video_files) == 0


@pytest.mark.unit
def test_converted_video_file_mismatched_stream_counts_raises_error(
    dummy_video_file: VideoFile, stream_source: StreamSource, mocker: MockerFixture
) -> None:
    """Test that ConvertedVideoFile raises ValueError for mismatched stream counts."""
    # Mock get_media_info to return a different number of streams
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(
            streams=(
                VideoStream(codec_type="video", index=0),
                AudioStream(codec_type="audio", index=1, channels=2),
            )
        ),
    )

    stream_sources = StreamSources(root=(stream_source,))  # Only one stream source
    with pytest.raises(ValueError, match="Mismatch in stream counts"):
        ConvertedVideoFile(
            path=dummy_video_file.path,
            stream_sources=stream_sources,
        )


@pytest.mark.unit
def test_converted_video_file_stream_with_sources_property(
    dummy_video_file: VideoFile, stream_source: StreamSource, mocker: MockerFixture
) -> None:
    """Test the stream_with_sources property of ConvertedVideoFile."""
    mock_stream = stream_source.source_stream
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        return_value=MediaInfo(streams=(mock_stream,)),
    )

    stream_sources = StreamSources(root=(stream_source,))
    converted_file = ConvertedVideoFile(
        path=dummy_video_file.path,
        stream_sources=stream_sources,
    )

    pairs = list(converted_file.stream_with_sources)
    assert len(pairs) == 1
    output_stream, source = pairs[0]
    assert output_stream == mock_stream
    assert source == stream_source
