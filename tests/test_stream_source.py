"""Unit tests for the StreamSource module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tests.helpers import StubConvertedVideoFile, stream_at
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_source import (
    Conversion,
    ConvertedVideoFile,
    Copy,
    EncodeVideo,
    StreamSource,
    StreamSources,
    StreamWithSource,
    streams_by_unique_index,
)
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


@pytest.fixture
def dummy_video_file(tmp_path: Path) -> VideoFile:
    """Create a dummy VideoFile instance."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.fixture
def stream_source(
    dummy_video_file: VideoFile,
) -> StreamSource[VideoStream, Conversion]:
    """Create a dummy StreamSource instance."""
    return StreamSource(
        source_stream=VideoStream(file=dummy_video_file, index=0),
        conversion=Copy(),
    )


@pytest.fixture
def stream_sources(tmp_path: Path) -> StreamSources:
    """Create StreamSources spanning two VideoFiles (video + two audios)."""
    path_a = tmp_path / "a.ts"
    path_b = tmp_path / "b.ts"
    path_a.touch()
    path_b.touch()
    file_a = VideoFile(path=path_a)
    file_b = VideoFile(path=path_b)

    return StreamSources(
        root=(
            StreamSource(
                source_stream=VideoStream(file=file_a, index=0),
                conversion=EncodeVideo(),
            ),
            StreamSource(
                source_stream=AudioStream(file=file_a, index=1),
                conversion=Copy(),
            ),
            StreamSource(
                source_stream=AudioStream(file=file_b, index=0),
                conversion=Copy(),
            ),
        )
    )


@pytest.mark.unit
def test_stream_sources_video_stream_sources_filters_video(
    stream_sources: StreamSources,
) -> None:
    """StreamSources.video_stream_sources returns only video sources."""
    # Act
    video_sources = stream_sources.video_stream_sources

    # Assert
    assert len(video_sources) == 1
    assert all(isinstance(s.source_stream, VideoStream) for s in video_sources)


@pytest.mark.unit
def test_stream_sources_audio_stream_sources_filters_audio(
    stream_sources: StreamSources,
) -> None:
    """StreamSources.audio_stream_sources returns only audio sources."""
    # Act
    audio_sources = stream_sources.audio_stream_sources

    # Assert
    assert len(audio_sources) == 2
    assert all(isinstance(s.source_stream, AudioStream) for s in audio_sources)


@pytest.mark.unit
def test_stream_sources_source_video_files_collects_unique_files(
    stream_sources: StreamSources,
) -> None:
    """StreamSources.source_video_files returns unique source VideoFiles."""
    # Act
    source_files = stream_sources.source_video_files

    # Assert
    assert len(source_files) == 2
    assert all(isinstance(f, VideoFile) for f in source_files)


@pytest.mark.unit
def test_stream_sources_properties_are_empty_when_no_sources() -> None:
    """StreamSources filter and file properties are empty for no sources."""
    # Arrange
    empty_stream_sources = StreamSources(root=())

    # Act & Assert
    assert len(empty_stream_sources.video_stream_sources) == 0
    assert len(empty_stream_sources.audio_stream_sources) == 0
    assert len(empty_stream_sources.source_video_files) == 0


@pytest.mark.unit
def test_converted_videofile_rejects_mismatched_stream_counts(
    dummy_video_file: VideoFile,
    stream_source: StreamSource[VideoStream, Conversion],
) -> None:
    """ConvertedVideoFile raises when stream_sources length mismatches streams."""
    # Arrange
    stream_sources = StreamSources(root=(stream_source,))

    # Act & Assert
    with pytest.raises(ValueError, match="Mismatch in stream counts"):
        StubConvertedVideoFile[StreamSources](
            path=dummy_video_file.path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(codec_type="video", index=0),
                    FFprobeStream(codec_type="audio", index=1, channels=2),
                )
            ),
            stream_sources=stream_sources,
        )


@pytest.mark.unit
def test_converted_videofile_rejects_when_output_indices_do_not_match_positions(
    dummy_video_file: VideoFile,
) -> None:
    """ConvertedVideoFile raises when output indices are not 0..n-1 for sources."""
    # Arrange
    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=VideoStream(file=dummy_video_file, index=0),
                conversion=EncodeVideo(),
            ),
            StreamSource(
                source_stream=AudioStream(file=dummy_video_file, index=1),
                conversion=Copy(),
            ),
        )
    )

    # Act & Assert
    with pytest.raises(ValueError, match="do not match stream_sources positions"):
        StubConvertedVideoFile[StreamSources](
            path=dummy_video_file.path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(codec_type="video", index=0),
                    FFprobeStream(codec_type="audio", index=2, channels=2),
                )
            ),
            stream_sources=stream_sources,
        )


@pytest.mark.unit
def test_streams_by_unique_index_rejects_duplicate_indices(
    dummy_video_file: VideoFile,
) -> None:
    """streams_by_unique_index raises when two streams share an index."""
    # Arrange
    streams: frozenset[Stream] = frozenset(
        {
            VideoStream(file=dummy_video_file, index=0),
            AudioStream(file=dummy_video_file, index=0),
        }
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Duplicate stream index 0"):
        streams_by_unique_index(streams)


@pytest.mark.unit
def test_converted_videofile_stream_with_sources_pairs_output_and_source(
    dummy_video_file: VideoFile,
    stream_source: StreamSource[VideoStream, Conversion],
) -> None:
    """ConvertedVideoFile.stream_with_sources pairs each output stream with its source."""
    # Arrange
    stream_sources = StreamSources(root=(stream_source,))
    converted_file = StubConvertedVideoFile[StreamSources](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(streams=(FFprobeStream(codec_type="video", index=0),)),
        stream_sources=stream_sources,
    )

    # Act
    items = list(converted_file.stream_with_sources)

    # Assert
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, StreamWithSource)
    assert item.stream == stream_at(converted_file.streams, 0)
    assert item.source == stream_source


@pytest.mark.unit
def test_converted_videofile_stream_with_sources_raises_on_type_mismatch(
    dummy_video_file: VideoFile,
) -> None:
    """ConvertedVideoFile.stream_with_sources raises when stream and source types differ."""
    # Arrange
    audio_stream_source: StreamSource[AudioStream, Conversion] = StreamSource(
        source_stream=AudioStream(file=dummy_video_file, index=0),
        conversion=Copy(),
    )
    converted_file = StubConvertedVideoFile[StreamSources](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(streams=(FFprobeStream(codec_type="video", index=0),)),
        stream_sources=StreamSources(root=(audio_stream_source,)),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Stream type mismatch for stream index 0"):
        list(converted_file.stream_with_sources)


@pytest.mark.unit
def test_converted_videofile_stream_with_sources_raises_when_output_index_missing(
    dummy_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """stream_with_sources raises when no output stream exists for a source position."""
    # Arrange
    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=VideoStream(file=dummy_video_file, index=0),
                conversion=EncodeVideo(),
            ),
            StreamSource(
                source_stream=AudioStream(file=dummy_video_file, index=1),
                conversion=Copy(),
            ),
        )
    )
    converted_file = StubConvertedVideoFile[StreamSources](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(codec_type="audio", index=1, channels=2),
            )
        ),
        stream_sources=stream_sources,
    )
    # Construction saw contiguous indices; simulate a gap only for pairing.
    mocker.patch.object(
        ConvertedVideoFile,
        "streams",
        new_callable=mocker.PropertyMock,
        return_value=frozenset(
            {
                VideoStream(file=dummy_video_file, index=0),
                AudioStream(file=dummy_video_file, index=2),
            }
        ),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="No output stream with index 1"):
        list(converted_file.stream_with_sources)
