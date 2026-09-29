"""Unit tests for the business logic in the video_encoder module."""

from pathlib import Path
from typing import Callable

import pytest

from tests.helpers import StubVideoFile, stream_at
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_source import Copy, EncodeVideo, StreamConversionPlan
from ts2mp4.video_encoder import (
    FileConversionPlanForVideoEncoding,
    StreamConversionPlanForVideoEncoding,
    build_file_conversion_plan_for_video_encoding,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


@pytest.fixture
def mock_video_file_factory(tmp_path: Path) -> Callable[..., VideoFile]:
    """Create a factory for mock VideoFile objects with specific stream configurations."""

    def _factory(
        video_streams: int = 1, audio_streams: int = 1, file_name: str = "test.ts"
    ) -> VideoFile:
        dummy_file = tmp_path / file_name
        dummy_file.touch()

        probe_streams: list[FFprobeStream] = []
        for i in range(video_streams):
            probe_streams.append(FFprobeStream(codec_type="video", index=i))
        for i in range(audio_streams):
            probe_streams.append(
                FFprobeStream(codec_type="audio", index=video_streams + i, channels=2)
            )

        return StubVideoFile(
            path=dummy_file, stub_probe=FFprobeOutput(streams=tuple(probe_streams))
        )

    return _factory


@pytest.mark.unit
def test_build_file_conversion_plan_for_video_encoding_orders_by_stream_index(
    tmp_path: Path,
) -> None:
    """Emit videos by index, then audios by index, even if probe order differs."""
    # Arrange
    path = tmp_path / "test.ts"
    path.touch()
    input_file = StubVideoFile(
        path=path,
        stub_probe=FFprobeOutput(
            streams=[
                FFprobeStream(codec_type="audio", index=2, channels=2),
                FFprobeStream(codec_type="video", index=1),
                FFprobeStream(codec_type="audio", index=3, channels=2),
                FFprobeStream(codec_type="video", index=0),
            ]
        ),
    )

    # Act
    file_conversion_plan = build_file_conversion_plan_for_video_encoding(
        input_file, crf=23, preset="medium"
    )

    # Assert
    assert [s.source_stream.index for s in file_conversion_plan] == [0, 1, 2, 3]
    assert [type(s.conversion_method) for s in file_conversion_plan] == [
        EncodeVideo,
        EncodeVideo,
        Copy,
        Copy,
    ]


@pytest.mark.unit
def test_build_file_conversion_plan_for_video_encoding_marks_video_encoded_and_audio_copied(
    mock_video_file_factory: Callable[..., VideoFile],
) -> None:
    """Mark video as encoded and audio as copied."""
    # Arrange
    input_file = mock_video_file_factory(video_streams=1, audio_streams=2)

    # Act
    file_conversion_plan = build_file_conversion_plan_for_video_encoding(
        input_file, crf=23, preset="medium"
    )

    # Assert
    assert isinstance(file_conversion_plan, FileConversionPlanForVideoEncoding)
    assert len(file_conversion_plan) == 3
    assert isinstance(file_conversion_plan[0].source_stream, VideoStream)
    assert isinstance(file_conversion_plan[0].conversion_method, EncodeVideo)
    assert isinstance(file_conversion_plan[1].source_stream, AudioStream)
    assert file_conversion_plan[1].conversion_method == Copy()
    assert isinstance(file_conversion_plan[2].source_stream, AudioStream)
    assert file_conversion_plan[2].conversion_method == Copy()


@pytest.mark.unit
def test_build_file_conversion_plan_for_video_encoding_encodes_video_with_libx265_settings(
    mock_video_file_factory: Callable[..., VideoFile],
) -> None:
    """Encode video with libx265, the given crf and preset, bwdif and cfr."""
    # Arrange
    input_file = mock_video_file_factory(video_streams=1, audio_streams=1)

    # Act
    file_conversion_plan = build_file_conversion_plan_for_video_encoding(
        input_file, crf=23, preset="medium"
    )

    # Assert
    assert file_conversion_plan[0].conversion_method == EncodeVideo(
        codec="libx265",
        crf=23,
        preset="medium",
        video_filter="bwdif",
        fps_mode="cfr",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "modifier, error_message",
    [
        pytest.param(
            "no_video",
            "At least one video stream is required.",
            id="no_video",
        ),
        pytest.param(
            "no_audio",
            "At least one audio stream is required.",
            id="no_audio",
        ),
        pytest.param(
            "multiple_sources",
            "All source streams must originate from the same VideoFile.",
            id="multiple_sources",
        ),
        pytest.param(
            "duplicate_streams",
            "Source streams must be unique.",
            id="duplicate_streams",
        ),
    ],
)
def test_file_conversion_plan_for_video_encoding_raises_on_invalid_plans(
    mock_video_file_factory: Callable[..., VideoFile],
    modifier: str,
    error_message: str,
) -> None:
    """Raise ValueError when FileConversionPlanForVideoEncoding validation fails."""
    # Arrange
    video_file = mock_video_file_factory()
    plans: list[StreamConversionPlanForVideoEncoding] = [
        StreamConversionPlan(
            source_stream=stream_at(video_file.streams, 0),
            conversion_method=EncodeVideo(codec="libx265", crf=23, preset="medium"),
        ),
        StreamConversionPlan(
            source_stream=stream_at(video_file.streams, 1),
            conversion_method=Copy(),
        ),
    ]

    if modifier == "no_video":
        plans = [s for s in plans if not isinstance(s.source_stream, VideoStream)]
    elif modifier == "no_audio":
        plans = [s for s in plans if not isinstance(s.source_stream, AudioStream)]
    elif modifier == "multiple_sources":
        other_video_file = mock_video_file_factory(file_name="other.ts")
        plans.append(
            StreamConversionPlan(
                source_stream=stream_at(other_video_file.streams, 0),
                conversion_method=EncodeVideo(codec="libx265", crf=23, preset="medium"),
            )
        )
    elif modifier == "duplicate_streams":
        plans.append(plans[0])

    # Act & Assert
    with pytest.raises(ValueError, match=error_message):
        FileConversionPlanForVideoEncoding(root=tuple(plans))
