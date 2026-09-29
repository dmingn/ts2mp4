"""Unit tests for the converted_video_file module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tests.helpers import StubConvertedVideoFile, stream_at
from ts2mp4.conversion_plan import (
    ConversionMethod,
    Copy,
    EncodeVideo,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import (
    ConvertedVideoFile,
    StreamWithConversionPlan,
    streams_by_unique_index,
)
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


@pytest.fixture
def dummy_video_file(tmp_path: Path) -> VideoFile:
    """Create a dummy VideoFile instance."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.fixture
def stream_conversion_plan(
    dummy_video_file: VideoFile,
) -> StreamConversionPlan[VideoStream, ConversionMethod]:
    """Create a dummy StreamConversionPlan instance."""
    return StreamConversionPlan(
        source_stream=VideoStream(file=dummy_video_file, index=0),
        conversion_method=Copy(),
    )


@pytest.mark.unit
def test_converted_videofile_rejects_mismatched_stream_counts(
    dummy_video_file: VideoFile,
    stream_conversion_plan: StreamConversionPlan[VideoStream, ConversionMethod],
) -> None:
    """ConvertedVideoFile raises when file_conversion_plan length mismatches streams."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=(stream_conversion_plan,))

    # Act & Assert
    with pytest.raises(ValueError, match="Mismatch in stream counts"):
        StubConvertedVideoFile[FileConversionPlan](
            path=dummy_video_file.path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(codec_type="video", index=0),
                    FFprobeStream(codec_type="audio", index=1, channels=2),
                )
            ),
            file_conversion_plan=file_conversion_plan,
        )


@pytest.mark.unit
def test_converted_videofile_rejects_when_output_indices_do_not_match_positions(
    dummy_video_file: VideoFile,
) -> None:
    """ConvertedVideoFile raises when output indices are not 0..n-1 for the plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(
        root=(
            StreamConversionPlan(
                source_stream=VideoStream(file=dummy_video_file, index=0),
                conversion_method=EncodeVideo(codec="libx265", crf=23, preset="medium"),
            ),
            StreamConversionPlan(
                source_stream=AudioStream(file=dummy_video_file, index=1),
                conversion_method=Copy(),
            ),
        )
    )

    # Act & Assert
    with pytest.raises(ValueError, match="do not match file_conversion_plan positions"):
        StubConvertedVideoFile[FileConversionPlan](
            path=dummy_video_file.path,
            stub_probe=FFprobeOutput(
                streams=(
                    FFprobeStream(codec_type="video", index=0),
                    FFprobeStream(codec_type="audio", index=2, channels=2),
                )
            ),
            file_conversion_plan=file_conversion_plan,
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
def test_converted_videofile_streams_with_conversion_plans_pairs_output_and_source(
    dummy_video_file: VideoFile,
    stream_conversion_plan: StreamConversionPlan[VideoStream, ConversionMethod],
) -> None:
    """ConvertedVideoFile.streams_with_conversion_plans pairs each output stream with its plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=(stream_conversion_plan,))
    converted_file = StubConvertedVideoFile[FileConversionPlan](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(streams=(FFprobeStream(codec_type="video", index=0),)),
        file_conversion_plan=file_conversion_plan,
    )

    # Act
    items = list(converted_file.streams_with_conversion_plans)

    # Assert
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, StreamWithConversionPlan)
    assert item.stream == stream_at(converted_file.streams, 0)
    assert item.conversion_plan == stream_conversion_plan


@pytest.mark.unit
def test_converted_videofile_streams_with_conversion_plans_raises_on_type_mismatch(
    dummy_video_file: VideoFile,
) -> None:
    """ConvertedVideoFile.streams_with_conversion_plans raises when stream and source types differ."""
    # Arrange
    audio_stream_plan: StreamConversionPlan[AudioStream, ConversionMethod] = (
        StreamConversionPlan(
            source_stream=AudioStream(file=dummy_video_file, index=0),
            conversion_method=Copy(),
        )
    )
    converted_file = StubConvertedVideoFile[FileConversionPlan](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(streams=(FFprobeStream(codec_type="video", index=0),)),
        file_conversion_plan=FileConversionPlan(root=(audio_stream_plan,)),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Stream type mismatch for stream index 0"):
        list(converted_file.streams_with_conversion_plans)


@pytest.mark.unit
def test_converted_videofile_streams_with_conversion_plans_raises_when_output_index_missing(
    dummy_video_file: VideoFile,
    mocker: MockerFixture,
) -> None:
    """streams_with_conversion_plans raises when no output stream exists for a plan position."""
    # Arrange
    file_conversion_plan = FileConversionPlan(
        root=(
            StreamConversionPlan(
                source_stream=VideoStream(file=dummy_video_file, index=0),
                conversion_method=EncodeVideo(codec="libx265", crf=23, preset="medium"),
            ),
            StreamConversionPlan(
                source_stream=AudioStream(file=dummy_video_file, index=1),
                conversion_method=Copy(),
            ),
        )
    )
    converted_file = StubConvertedVideoFile[FileConversionPlan](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(codec_type="audio", index=1, channels=2),
            )
        ),
        file_conversion_plan=file_conversion_plan,
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
        list(converted_file.streams_with_conversion_plans)
