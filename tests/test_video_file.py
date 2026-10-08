"""Unit tests for the VideoFile module."""

from pathlib import Path

import pytest

from tests.helpers import TS_TIME_BASE, StubVideoFile, stream_at
from ts2mp4.ffmpeg import SubprocessFFmpegRunner
from ts2mp4.ffmpeg_input_args import build_input_args
from ts2mp4.ffprobe_schema import (
    FFprobeFormat,
    FFprobeOutput,
    FFprobeStream,
    FFprobeStreamTags,
)
from ts2mp4.video_file import (
    AudioStream,
    OtherStream,
    SubtitleStream,
    VideoFile,
    VideoStream,
)


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
                FFprobeStream(time_base=TS_TIME_BASE, codec_type="video", index=0),
                FFprobeStream(
                    time_base=TS_TIME_BASE, codec_type="audio", index=1, channels=2
                ),
                FFprobeStream(
                    time_base=TS_TIME_BASE, codec_type="audio", index=2, channels=0
                ),
                FFprobeStream(
                    time_base=TS_TIME_BASE, codec_type="audio", index=3, channels=6
                ),
                FFprobeStream(
                    time_base=TS_TIME_BASE,
                    codec_type="subtitle",
                    index=4,
                    codec_name="arib_caption",
                ),
                FFprobeStream(
                    time_base=TS_TIME_BASE,
                    codec_type="subtitle",
                    index=5,
                    codec_name="dvb_subtitle",
                ),
                FFprobeStream(
                    time_base=TS_TIME_BASE,
                    codec_type="data",
                    index=6,
                    codec_name="bin_data",
                ),
            )
        ),
    )


@pytest.mark.unit
def test_audiostream_channels_derives_from_probe(mixed_video_file: VideoFile) -> None:
    """AudioStream.channels is read from the probed stream at this index."""
    # Arrange
    stream = AudioStream(file=mixed_video_file, index=3)

    # Act
    channels = stream.channels

    # Assert
    assert channels == 6


@pytest.mark.unit
def test_videofile_streams_maps_probe_output_to_domain_types(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.streams maps probed entries to Video/Audio/Subtitle/OtherStream."""
    # Act
    streams = mixed_video_file.streams

    # Assert
    assert isinstance(stream_at(streams, 0), VideoStream)
    assert isinstance(stream_at(streams, 1), AudioStream)
    assert isinstance(stream_at(streams, 4), SubtitleStream)
    assert isinstance(stream_at(streams, 6), OtherStream)
    assert stream_at(streams, 0).codec_type == "video"
    assert stream_at(streams, 1).codec_type == "audio"
    assert stream_at(streams, 4).codec_type == "subtitle"
    assert stream_at(streams, 6).codec_type == "data"


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


@pytest.mark.unit
def test_videofile_valid_subtitle_streams_includes_every_subtitle_codec(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.valid_subtitle_streams includes subtitle streams of any codec."""
    # Act
    valid_subtitle_streams = mixed_video_file.valid_subtitle_streams

    # Assert
    assert valid_subtitle_streams == frozenset(
        {
            SubtitleStream(file=mixed_video_file, index=4),
            SubtitleStream(file=mixed_video_file, index=5),
        }
    )


@pytest.mark.unit
def test_videofile_valid_streams_includes_subtitle_streams(
    mixed_video_file: VideoFile,
) -> None:
    """VideoFile.valid_streams includes the valid subtitle streams."""
    # Act
    valid_streams = mixed_video_file.valid_streams

    # Assert
    assert mixed_video_file.valid_subtitle_streams <= valid_streams


@pytest.mark.unit
@pytest.mark.parametrize(
    "format_name, expected",
    [
        pytest.param("matroska,webm", True, id="matroska"),
        pytest.param("mpegts", False, id="mpegts"),
        pytest.param(None, False, id="unknown"),
    ],
)
def test_videofile_is_matroska_reads_format_name(
    dummy_path: Path, format_name: str | None, expected: bool
) -> None:
    """VideoFile.is_matroska is True if the format names include matroska."""
    # Arrange
    video_file = StubVideoFile(
        path=dummy_path,
        stub_probe=FFprobeOutput(format=FFprobeFormat(format_name=format_name)),
    )

    # Act
    is_matroska = video_file.is_matroska

    # Assert
    assert is_matroska == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "format_name, ffprobe_stream, expected",
    [
        pytest.param(
            "mpegts",
            FFprobeStream(
                time_base=TS_TIME_BASE, codec_type="audio", index=0, duration=20.5
            ),
            20.5,
            id="mpegts",
        ),
        pytest.param(
            "mpegts",
            FFprobeStream(
                time_base=TS_TIME_BASE,
                codec_type="audio",
                index=0,
                tags=FFprobeStreamTags(duration=30.0),
            ),
            None,
            id="mpegts_ignores_duration_tag",
        ),
        pytest.param(
            "matroska,webm",
            FFprobeStream(
                time_base=TS_TIME_BASE,
                codec_type="audio",
                index=0,
                start_time=0.5,
                tags=FFprobeStreamTags(duration=30.0),
            ),
            29.5,
            id="matroska",
        ),
        pytest.param(
            "matroska,webm",
            FFprobeStream(
                time_base=TS_TIME_BASE,
                codec_type="audio",
                index=0,
                tags=FFprobeStreamTags(duration=30.0),
            ),
            None,
            id="matroska_without_start_time",
        ),
        pytest.param(
            "matroska,webm",
            FFprobeStream(
                time_base=TS_TIME_BASE, codec_type="audio", index=0, start_time=0.5
            ),
            None,
            id="matroska_without_duration_tag",
        ),
    ],
)
def test_stream_duration_depends_on_container(
    dummy_path: Path,
    format_name: str,
    ffprobe_stream: FFprobeStream,
    expected: float | None,
) -> None:
    """Stream.duration reads the end time in the DURATION tag only for Matroska."""
    # Arrange
    stream = AudioStream(
        file=StubVideoFile(
            path=dummy_path,
            stub_probe=FFprobeOutput(
                streams=(ffprobe_stream,),
                format=FFprobeFormat(format_name=format_name),
            ),
        ),
        index=0,
    )

    # Act
    duration = stream.duration

    # Assert
    assert duration == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "file_start_time, stream_start_time, expected",
    [
        pytest.param(100.0, 100.5, 0.5, id="known"),
        pytest.param(None, 100.5, None, id="no_file_start_time"),
        pytest.param(100.0, None, None, id="no_stream_start_time"),
    ],
)
def test_stream_start_offset_is_relative_to_file_start(
    dummy_path: Path,
    file_start_time: float | None,
    stream_start_time: float | None,
    expected: float | None,
) -> None:
    """Stream.start_offset is the stream start time minus the file start time."""
    # Arrange
    stream = AudioStream(
        file=StubVideoFile(
            path=dummy_path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(
                        time_base=TS_TIME_BASE,
                        codec_type="audio",
                        index=0,
                        start_time=stream_start_time,
                    ),
                ),
                format=FFprobeFormat(start_time=file_start_time),
            ),
        ),
        index=0,
    )

    # Act
    start_offset = stream.start_offset

    # Assert
    assert start_offset == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "duration, expected",
    [
        pytest.param(20.0, 20.5, id="known"),
        pytest.param(None, None, id="no_duration"),
    ],
)
def test_stream_end_offset_adds_duration_to_start_offset(
    dummy_path: Path, duration: float | None, expected: float | None
) -> None:
    """Stream.end_offset is the stream start offset plus its duration."""
    # Arrange
    stream = AudioStream(
        file=StubVideoFile(
            path=dummy_path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(
                        time_base=TS_TIME_BASE,
                        codec_type="audio",
                        index=0,
                        start_time=100.5,
                        duration=duration,
                    ),
                ),
                format=FFprobeFormat(start_time=100.0),
            ),
        ),
        index=0,
    )

    # Act
    end_offset = stream.end_offset

    # Assert
    assert end_offset == expected


@pytest.mark.integration
def test_stream_duration_of_matroska_file(ts_file: Path, tmp_path: Path) -> None:
    """Every stream of a Matroska file reports a positive duration."""
    # Arrange
    mkv_path = tmp_path / "copied.mkv"
    SubprocessFFmpegRunner().run(
        [
            *build_input_args(ts_file),
            "-map",
            "0",
            "-c",
            "copy",
            "-f",
            "matroska",
            str(mkv_path),
        ]
    )

    # Act
    durations = [stream.duration for stream in VideoFile(path=mkv_path).streams]

    # Assert
    assert all(duration is not None and duration > 0 for duration in durations)


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
