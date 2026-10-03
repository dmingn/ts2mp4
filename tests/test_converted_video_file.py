"""Unit tests for the converted_video_file module."""

from pathlib import Path

import pytest

from tests.helpers import StubConvertedVideoFile, stream_at
from ts2mp4.conversion_plan import (
    ConversionMethod,
    Copy,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import (
    StreamWithConversionPlan,
)
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


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
def test_converted_videofile_rejects_stream_type_mismatch(
    dummy_video_file: VideoFile,
) -> None:
    """ConvertedVideoFile raises when an output stream and its plan differ in kind."""
    # Arrange
    audio_stream_plan: StreamConversionPlan[AudioStream, ConversionMethod] = (
        StreamConversionPlan(
            source_stream=AudioStream(file=dummy_video_file, index=0),
            conversion_method=Copy(),
        )
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Stream type mismatch for stream index 0"):
        StubConvertedVideoFile[FileConversionPlan](
            path=dummy_video_file.path,
            stub_probe=FFprobeOutput(
                streams=(FFprobeStream(codec_type="video", index=0),)
            ),
            file_conversion_plan=FileConversionPlan(root=(audio_stream_plan,)),
        )


@pytest.mark.unit
def test_converted_videofile_streams_with_conversion_plans_pairs_output_stream_with_plan(
    dummy_video_file: VideoFile,
    stream_conversion_plan: StreamConversionPlan[VideoStream, ConversionMethod],
) -> None:
    """ConvertedVideoFile.streams_with_conversion_plans pairs each output stream with its plan."""
    # Arrange
    converted_file = StubConvertedVideoFile[FileConversionPlan](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(streams=(FFprobeStream(codec_type="video", index=0),)),
        file_conversion_plan=FileConversionPlan(root=(stream_conversion_plan,)),
    )

    # Act
    streams_with_conversion_plans = converted_file.streams_with_conversion_plans

    # Assert
    assert streams_with_conversion_plans == (
        StreamWithConversionPlan(
            stream=stream_at(converted_file.streams, 0),
            conversion_plan=stream_conversion_plan,
        ),
    )


@pytest.mark.unit
def test_converted_videofile_streams_with_conversion_plans_follows_output_index_order(
    dummy_video_file: VideoFile,
) -> None:
    """streams_with_conversion_plans pairs plan i with output index i, whatever the probe order."""
    # Arrange
    video_plan: StreamConversionPlan[VideoStream, ConversionMethod] = (
        StreamConversionPlan(
            source_stream=VideoStream(file=dummy_video_file, index=0),
            conversion_method=Copy(),
        )
    )
    audio_plan: StreamConversionPlan[AudioStream, ConversionMethod] = (
        StreamConversionPlan(
            source_stream=AudioStream(file=dummy_video_file, index=1),
            conversion_method=Copy(),
        )
    )
    converted_file = StubConvertedVideoFile[FileConversionPlan](
        path=dummy_video_file.path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="audio", index=1, channels=2),
                FFprobeStream(codec_type="video", index=0),
            )
        ),
        file_conversion_plan=FileConversionPlan(root=(video_plan, audio_plan)),
    )

    # Act
    streams_with_conversion_plans = converted_file.streams_with_conversion_plans

    # Assert
    assert [
        (pair.stream.index, pair.conversion_plan)
        for pair in streams_with_conversion_plans
    ] == [(0, video_plan), (1, audio_plan)]
