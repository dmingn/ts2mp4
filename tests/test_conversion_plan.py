"""Unit tests for the conversion_plan module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.conversion_plan import (
    Copy,
    EncodeVideo,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


@pytest.fixture
def file_conversion_plan(tmp_path: Path) -> FileConversionPlan:
    """Create FileConversionPlan spanning two VideoFiles (video + two audios)."""
    path_a = tmp_path / "a.ts"
    path_b = tmp_path / "b.ts"
    path_a.touch()
    path_b.touch()
    file_a = VideoFile(path=path_a)
    file_b = VideoFile(path=path_b)

    return FileConversionPlan(
        root=(
            StreamConversionPlan(
                source_stream=VideoStream(file=file_a, index=0),
                conversion_method=EncodeVideo(codec="libx265", crf=23, preset="medium"),
            ),
            StreamConversionPlan(
                source_stream=AudioStream(file=file_a, index=1),
                conversion_method=Copy(),
            ),
            StreamConversionPlan(
                source_stream=AudioStream(file=file_b, index=0),
                conversion_method=Copy(),
            ),
        )
    )


@pytest.mark.unit
def test_file_conversion_plan_video_stream_plans_filters_video(
    file_conversion_plan: FileConversionPlan,
) -> None:
    """FileConversionPlan.video_stream_plans returns only video plans."""
    # Act
    video_plans = file_conversion_plan.video_stream_plans

    # Assert
    assert len(video_plans) == 1
    assert all(isinstance(s.source_stream, VideoStream) for s in video_plans)


@pytest.mark.unit
def test_file_conversion_plan_audio_stream_plans_filters_audio(
    file_conversion_plan: FileConversionPlan,
) -> None:
    """FileConversionPlan.audio_stream_plans returns only audio plans."""
    # Act
    audio_plans = file_conversion_plan.audio_stream_plans

    # Assert
    assert len(audio_plans) == 2
    assert all(isinstance(s.source_stream, AudioStream) for s in audio_plans)


@pytest.mark.unit
def test_file_conversion_plan_source_video_files_collects_unique_files(
    file_conversion_plan: FileConversionPlan,
) -> None:
    """FileConversionPlan.source_video_files returns unique source VideoFiles."""
    # Act
    source_files = file_conversion_plan.source_video_files

    # Assert
    assert len(source_files) == 2
    assert all(isinstance(f, VideoFile) for f in source_files)


@pytest.mark.unit
def test_file_conversion_plan_default_stream_indices_selects_from_source_streams(
    mocker: MockerFixture, file_conversion_plan: FileConversionPlan
) -> None:
    """FileConversionPlan.default_stream_indices selects among source streams in order."""
    # Arrange
    mock_get_default_stream_indices = mocker.patch(
        "ts2mp4.conversion_plan.get_default_stream_indices",
        return_value=frozenset({0, 1}),
    )

    # Act
    default_stream_indices = file_conversion_plan.default_stream_indices

    # Assert
    assert default_stream_indices == frozenset({0, 1})
    mock_get_default_stream_indices.assert_called_once_with(
        [plan.source_stream for plan in file_conversion_plan]
    )


@pytest.mark.unit
def test_file_conversion_plan_properties_are_empty_when_no_plans() -> None:
    """FileConversionPlan filter and file properties are empty for no plans."""
    # Arrange
    empty_file_conversion_plan = FileConversionPlan(root=())

    # Act & Assert
    assert len(empty_file_conversion_plan.video_stream_plans) == 0
    assert len(empty_file_conversion_plan.audio_stream_plans) == 0
    assert len(empty_file_conversion_plan.source_video_files) == 0
