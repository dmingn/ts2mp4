"""Unit tests for the business logic in the ts2mp4 module."""

from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.ts2mp4 import (
    StreamSourcesForInitialConversion,
    _build_stream_sources,
)
from ts2mp4.video_file import (
    ConversionType,
    StreamSource,
    StreamSources,
    VideoFile,
)


@pytest.fixture
def mock_video_file_factory(
    mocker: MockerFixture, tmp_path: Path
) -> Callable[..., VideoFile]:
    """Create a factory for mock VideoFile objects with specific stream configurations."""

    def _factory(
        video_streams: int = 1, audio_streams: int = 1, file_name: str = "test.ts"
    ) -> VideoFile:
        dummy_file = tmp_path / file_name
        dummy_file.touch()

        streams = []
        for i in range(video_streams):
            streams.append(Stream(codec_type="video", index=i))
        for i in range(audio_streams):
            streams.append(
                Stream(codec_type="audio", index=video_streams + i, channels=2)
            )

        media_info = MediaInfo(streams=tuple(streams))
        mocker.patch("ts2mp4.video_file.get_media_info", return_value=media_info)

        return VideoFile(path=dummy_file)

    return _factory


@pytest.mark.unit
def test_build_stream_sources(
    mock_video_file_factory: Callable[..., VideoFile],
) -> None:
    """Test that _build_stream_sources correctly creates stream sources."""
    # Arrange
    input_file = mock_video_file_factory(video_streams=1, audio_streams=2)

    # Act
    stream_sources = _build_stream_sources(input_file)

    # Assert
    assert isinstance(stream_sources, StreamSourcesForInitialConversion)
    assert len(stream_sources) == 3
    # Video stream should be CONVERTED
    assert stream_sources[0].source_stream.codec_type == "video"
    assert stream_sources[0].conversion_type == ConversionType.CONVERTED
    # Audio streams should be COPIED
    assert stream_sources[1].source_stream.codec_type == "audio"
    assert stream_sources[1].conversion_type == ConversionType.COPIED
    assert stream_sources[2].source_stream.codec_type == "audio"
    assert stream_sources[2].conversion_type == ConversionType.COPIED


@pytest.fixture
def valid_stream_sources(
    mock_video_file_factory: Callable[..., VideoFile],
) -> StreamSources:
    """Fixture to create a valid StreamSources object for validation tests."""
    video_file = mock_video_file_factory()
    video_stream = StreamSource(
        source_video_file=video_file,
        source_stream_index=0,
        conversion_type=ConversionType.CONVERTED,
    )
    audio_stream = StreamSource(
        source_video_file=video_file,
        source_stream_index=1,
        conversion_type=ConversionType.COPIED,
    )
    return StreamSources((video_stream, audio_stream))


@pytest.mark.unit
def test_stream_sources_for_initial_conversion_success(
    valid_stream_sources: StreamSources,
) -> None:
    """Test that StreamSourcesForInitialConversion can be instantiated with valid data."""
    # This should not raise an error
    instance = StreamSourcesForInitialConversion(valid_stream_sources)
    assert instance is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "modifier, error_message",
    [
        ("no_video", "At least one video stream is required."),
        ("no_audio", "At least one audio stream is required."),
        ("video_not_converted", "All video streams must be converted."),
        ("audio_not_copied", "All audio streams must be copied."),
        (
            "multiple_sources",
            "All stream sources must originate from the same VideoFile.",
        ),
        (
            "unsupported_stream_type",
            "Stream sources must only contain video or audio streams.",
        ),
    ],
)
def test_stream_sources_for_initial_conversion_failures(
    valid_stream_sources: StreamSources,
    mock_video_file_factory: Callable[..., VideoFile],
    modifier: str,
    error_message: str,
    mocker: MockerFixture,
) -> None:
    """Test the validation rules in StreamSourcesForInitialConversion.__new__."""
    video_file = valid_stream_sources[0].source_video_file
    sources = list(valid_stream_sources)

    if modifier == "no_video":
        sources = [s for s in sources if s.source_stream.codec_type != "video"]
    elif modifier == "no_audio":
        sources = [s for s in sources if s.source_stream.codec_type != "audio"]
    elif modifier == "video_not_converted":
        sources[0] = StreamSource(
            source_video_file=video_file,
            source_stream_index=0,
            conversion_type=ConversionType.COPIED,
        )
    elif modifier == "audio_not_copied":
        sources[1] = StreamSource(
            source_video_file=video_file,
            source_stream_index=1,
            conversion_type=ConversionType.CONVERTED,
        )
    elif modifier == "multiple_sources":
        other_video_file = mock_video_file_factory(file_name="other.ts")
        sources.append(
            StreamSource(
                source_video_file=other_video_file,
                source_stream_index=0,
                conversion_type=ConversionType.CONVERTED,
            )
        )
    elif modifier == "unsupported_stream_type":
        # Manually create a new MediaInfo with the subtitle stream
        subtitle_stream = Stream(codec_type="subtitle", index=2)
        original_streams = video_file.media_info.streams
        new_media_info = MediaInfo(streams=original_streams + (subtitle_stream,))
        mocker.patch("ts2mp4.video_file.get_media_info", return_value=new_media_info)
        sources.append(
            StreamSource(
                source_video_file=video_file,
                source_stream_index=2,
                conversion_type=ConversionType.COPIED,
            )
        )

    with pytest.raises(ValueError, match=error_message):
        StreamSourcesForInitialConversion(StreamSources(sources))
