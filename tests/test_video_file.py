"""Unit tests for the VideoFile module."""

from pathlib import Path

import pytest

from tests.helpers import StubVideoFile, stream_at
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.video_file import AudioStream, OtherStream, VideoFile, VideoStream


@pytest.fixture
def dummy_path(tmp_path: Path) -> Path:
    """Create an empty file to back a VideoFile."""
    path = tmp_path / "test.ts"
    path.touch()
    return path


@pytest.fixture
def mixed_video_file(dummy_path: Path) -> VideoFile:
    """Create a VideoFile with mixed video, audio, and other streams."""
    return StubVideoFile(
        path=dummy_path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(codec_type="audio", index=1, channels=2),
                FFprobeStream(codec_type="audio", index=2, channels=0),
                FFprobeStream(codec_type="audio", index=3, channels=6),
                FFprobeStream(codec_type="subtitle", index=4),
            )
        ),
    )


@pytest.mark.unit
def test_videofile_streams_copies_probe_metadata(dummy_path: Path) -> None:
    """VideoFile.streams copies probed metadata into the stream fields."""
    # Arrange
    video_file = StubVideoFile(
        path=dummy_path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(
                    index=0, codec_type="video", duration=10.0, width=1920, height=1080
                ),
                FFprobeStream(
                    index=1,
                    codec_type="audio",
                    duration=9.5,
                    codec_name="aac",
                    profile="LC",
                    bit_rate=192000,
                    channels=6,
                    sample_rate=48000,
                ),
            )
        ),
    )

    # Act
    streams = video_file.streams

    # Assert
    assert streams == frozenset(
        {
            VideoStream(
                file=video_file,
                index=0,
                duration=10.0,
                width=1920,
                height=1080,
            ),
            AudioStream(
                file=video_file,
                index=1,
                duration=9.5,
                codec_name="aac",
                profile="LC",
                bit_rate=192000,
                channels=6,
                sample_rate=48000,
            ),
        }
    )


@pytest.mark.unit
def test_videofile_streams_maps_probe_output_to_domain_types(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.streams maps probed entries to Video/Audio/OtherStream."""
    # Act
    streams = mixed_video_file.streams

    # Assert
    assert isinstance(stream_at(streams, 0), VideoStream)
    assert isinstance(stream_at(streams, 1), AudioStream)
    other = stream_at(streams, 4)
    assert isinstance(other, OtherStream)
    assert other.codec_type == "subtitle"


@pytest.mark.unit
def test_videofile_streams_binds_each_stream_to_the_file(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.streams binds every domain stream to the owning file."""
    # Act
    streams = mixed_video_file.streams

    # Assert
    assert all(stream.file == mixed_video_file for stream in streams)


@pytest.mark.unit
def test_basestream_sorts_by_file_path_then_index(tmp_path: Path) -> None:
    """BaseStream total order is file.path, then index."""
    # Arrange
    path_a = tmp_path / "a.ts"
    path_b = tmp_path / "b.ts"
    path_a.touch()
    path_b.touch()
    file_a = VideoFile(path=path_a)
    file_b = VideoFile(path=path_b)
    unordered = frozenset(
        {
            AudioStream(file=file_b, index=1),
            VideoStream(file=file_a, index=0),
            AudioStream(file=file_a, index=1),
            VideoStream(file=file_b, index=0),
        }
    )

    # Act
    ordered = sorted(unordered)

    # Assert
    assert [(stream.file.path, stream.index) for stream in ordered] == [
        (path_a, 0),
        (path_a, 1),
        (path_b, 0),
        (path_b, 1),
    ]


@pytest.mark.unit
def test_videofile_valid_audio_streams_excludes_zero_channels(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.valid_audio_streams excludes audio streams with channels <= 0."""
    # Act
    valid_audio_streams = mixed_video_file.valid_audio_streams

    # Assert
    assert len(valid_audio_streams) == 2
    assert all(
        stream.channels is not None and stream.channels > 0
        for stream in valid_audio_streams
    )


@pytest.mark.integration
def test_videofile_streams_maps_real_ts_file(ts_file: Path) -> None:
    """VideoFile.streams maps a real TS fixture to domain video and audio streams."""
    # Arrange
    video_file = VideoFile(path=ts_file)

    # Act
    streams = video_file.streams
    video_stream = stream_at(streams, 0)

    # Assert
    assert isinstance(video_stream, VideoStream)
    assert video_stream.width == 1280
    assert video_stream.height == 720
    assert isinstance(stream_at(streams, 1), AudioStream)
    assert isinstance(stream_at(streams, 2), AudioStream)
    assert all(stream.file == video_file for stream in streams)
