"""Unit and integration tests for the quality_check module."""

import math
from collections.abc import AsyncIterator
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.conversion import execute_conversion
from ts2mp4.conversion_plan import (
    ConversionMethod,
    Copy,
    EncodeAudio,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import ConvertedVideoFile, StreamWithConversionPlan
from ts2mp4.ffmpeg import FFmpegProcessError, SubprocessFFmpegRunner
from ts2mp4.quality_check import (
    AudioQualityMetrics,
    build_quality_filter_complex,
    check_audio_quality,
    format_audio_quality_segments,
    get_audio_quality_metrics,
    parse_audio_quality_metrics,
)
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


class _FailFirstCallFFmpegRunner(FakeFFmpegRunner):
    """A FakeFFmpegRunner whose first stream_stderr call fails."""

    async def stream_stderr(self, args: list[str]) -> AsyncIterator[str]:
        """Raise FFmpegProcessError on the first call, then yield the fixed lines."""
        if not self.calls:
            self.calls.append(args)
            raise FFmpegProcessError("Error")

        async for line in super().stream_stderr(args):
            yield line


async def _lines(ffmpeg_output: str) -> AsyncGenerator[str, None]:
    for line in ffmpeg_output.splitlines():
        yield line


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ffmpeg_output, expected",
    [
        pytest.param(
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: inf dB\n"
            "[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: inf dB",
            AudioQualityMetrics(apsnr=((float("inf"),),), asdr=((float("inf"),),)),
            id="infinite_values",
        ),
        pytest.param(
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: 30.00 dB",
            AudioQualityMetrics(apsnr=((30.0,),), asdr=()),
            id="apsnr_only",
        ),
        pytest.param(
            "[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: -5.25 dB",
            AudioQualityMetrics(apsnr=(), asdr=((-5.25,),)),
            id="negative_asdr_only",
        ),
        pytest.param(
            "No metrics here",
            AudioQualityMetrics(apsnr=(), asdr=()),
            id="no_metrics",
        ),
        pytest.param(
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: invalid dB",
            AudioQualityMetrics(apsnr=(), asdr=()),
            id="unparsable_value",
        ),
        pytest.param(
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 10.0 dB\n"
            "[Parsed_apsnr_0 @ 0x123] PSNR ch1: 20.0 dB",
            AudioQualityMetrics(apsnr=((10.0, 20.0),), asdr=()),
            id="channels_of_one_segment",
        ),
        pytest.param(
            "[Parsed_apsnr_0 @ 0x123] PSNR ch1: 42.0 dB",
            AudioQualityMetrics(apsnr=((42.0,),), asdr=()),
            id="segment_without_ch0",
        ),
        pytest.param(
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 10.0 dB\n"
            "[Parsed_apsnr_0 @ 0x123] PSNR ch1: 20.0 dB\n"
            "[Parsed_apsnr_0 @ 0x456] PSNR ch0: 30.0 dB",
            AudioQualityMetrics(apsnr=((10.0, 20.0), (30.0,)), asdr=()),
            id="ch0_starts_new_segment",
        ),
    ],
)
async def test_parse_audio_quality_metrics(
    ffmpeg_output: str, expected: AudioQualityMetrics
) -> None:
    """parse_audio_quality_metrics reads every segment and channel of each metric."""
    # Act
    metrics = await parse_audio_quality_metrics(_lines(ffmpeg_output))

    # Assert
    assert metrics == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_audio_quality_metrics_reads_negative_nan_as_nan() -> None:
    """parse_audio_quality_metrics reads FFmpeg's -nan as NaN."""
    # Act
    metrics = await parse_audio_quality_metrics(
        _lines("[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: -nan dB")
    )

    # Assert
    assert math.isnan(metrics.asdr[0][0])


@pytest.mark.unit
def test_format_audio_quality_segments_describes_each_segment() -> None:
    """format_audio_quality_segments returns one description per segment."""
    # Arrange
    metrics = AudioQualityMetrics(
        apsnr=((30.0, 31.0), (40.0,)),
        asdr=((20.0, 21.0), (25.0,)),
    )

    # Act
    descriptions = format_audio_quality_segments(metrics)

    # Assert
    assert descriptions == (
        "APSNR=[30.00, 31.00]dB ASDR=[20.00, 21.00]dB",
        "APSNR=[40.00]dB ASDR=[25.00]dB",
    )


@pytest.mark.unit
def test_format_audio_quality_segments_omits_missing_metric() -> None:
    """format_audio_quality_segments omits a metric that has no value for a segment."""
    # Arrange
    metrics = AudioQualityMetrics(apsnr=((30.0,), (40.0,)), asdr=((20.0,),))

    # Act
    descriptions = format_audio_quality_segments(metrics)

    # Assert
    assert descriptions == ("APSNR=[30.00]dB ASDR=[20.00]dB", "APSNR=[40.00]dB")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_metrics_for_encoded_audio(
    tmp_path: Path,
) -> None:
    """Return APSNR/ASDR for each encoded audio stream and skip others."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(
        stderr_lines=[
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB",
            "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB",
        ]
    )

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    stream2 = VideoStream(file=converted_video, index=1)
    stream3 = AudioStream(file=converted_video, index=2)

    plan1: StreamConversionPlan[AudioStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=EncodeAudio(codec="aac"),
        source_stream=AudioStream(file=original_file, index=0),
    )
    plan2: StreamConversionPlan[VideoStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=Copy(),
        source_stream=VideoStream(file=original_file, index=1),
    )
    plan3: StreamConversionPlan[AudioStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=EncodeAudio(codec="aac"),
        source_stream=AudioStream(file=original_file, index=1),
    )

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.streams_with_conversion_plans = [
        StreamWithConversionPlan(stream=stream1, conversion_plan=plan1),
        StreamWithConversionPlan(stream=stream2, conversion_plan=plan2),
        StreamWithConversionPlan(stream=stream3, conversion_plan=plan3),
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file, ffmpeg_runner)

    # Assert
    assert len(metrics) == 2
    assert 0 in metrics
    assert 2 in metrics
    assert metrics[0] == AudioQualityMetrics(apsnr=((30.0,),), asdr=((25.0,),))
    assert metrics[2] == AudioQualityMetrics(apsnr=((30.0,),), asdr=((25.0,),))
    assert len(ffmpeg_runner.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_skips_failed_stream(
    tmp_path: Path,
) -> None:
    """Omit a stream when FFmpeg fails and keep metrics for later streams."""
    # Arrange
    ffmpeg_runner = _FailFirstCallFFmpegRunner(
        stderr_lines=[
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB",
            "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB",
        ]
    )

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    stream2 = AudioStream(file=converted_video, index=2)

    plan1: StreamConversionPlan[AudioStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=EncodeAudio(codec="aac"),
        source_stream=AudioStream(file=original_file, index=0),
    )
    plan2: StreamConversionPlan[AudioStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=EncodeAudio(codec="aac"),
        source_stream=AudioStream(file=original_file, index=1),
    )

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.streams_with_conversion_plans = [
        StreamWithConversionPlan(stream=stream1, conversion_plan=plan1),
        StreamWithConversionPlan(stream=stream2, conversion_plan=plan2),
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file, ffmpeg_runner)

    # Assert
    assert len(metrics) == 1
    assert 2 in metrics
    assert metrics[2] == AudioQualityMetrics(apsnr=((30.0,),), asdr=((25.0,),))
    assert len(ffmpeg_runner.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_empty_when_no_metrics_parsed(
    tmp_path: Path,
) -> None:
    """Return an empty dict when FFmpeg output contains no parseable metrics."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(stderr_lines=["No metrics here"])

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    plan1: StreamConversionPlan[AudioStream, ConversionMethod] = StreamConversionPlan(
        conversion_method=EncodeAudio(codec="aac"),
        source_stream=AudioStream(file=original_file, index=0),
    )
    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.streams_with_conversion_plans = [
        StreamWithConversionPlan(stream=stream1, conversion_plan=plan1)
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file, ffmpeg_runner)

    # Assert
    assert len(metrics) == 0


@pytest.mark.unit
def test_build_quality_filter_complex_compares_inputs_directly_without_filter() -> None:
    """build_quality_filter_complex feeds both inputs to apsnr and asdr as they are."""
    # Act
    filter_complex = build_quality_filter_complex("[0:1]", "[1:2]", None)

    # Assert
    assert filter_complex == "[0:1][1:2]apsnr;[0:1][1:2]asdr"


@pytest.mark.unit
def test_build_quality_filter_complex_applies_filter_to_original_input() -> None:
    """build_quality_filter_complex passes the original input through audio_filter."""
    # Act
    filter_complex = build_quality_filter_complex(
        "[0:1]", "[1:2]", "aformat=channel_layouts=5.1"
    )

    # Assert
    assert filter_complex == (
        "[0:1]aformat=channel_layouts=5.1[original_apsnr];"
        "[original_apsnr][1:2]apsnr;"
        "[0:1]aformat=channel_layouts=5.1[original_asdr];"
        "[original_asdr][1:2]asdr"
    )


@pytest.mark.unit
def test_check_audio_quality(mocker: MockerFixture) -> None:
    """Test the synchronous wrapper for get_audio_quality_metrics."""
    # Arrange
    mock_async_func = mocker.patch("ts2mp4.quality_check.get_audio_quality_metrics")
    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    ffmpeg_runner = FakeFFmpegRunner()

    # Act
    check_audio_quality(mock_converted_file, ffmpeg_runner)

    # Assert
    mock_async_func.assert_called_once_with(mock_converted_file, ffmpeg_runner)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_positive_metrics_for_real_file(
    ts_file: Path,
) -> None:
    """Return positive APSNR/ASDR for each valid audio stream of a real file."""
    # Arrange
    video_file = VideoFile(path=ts_file)
    file_conversion_plan: list[StreamConversionPlan[Stream, ConversionMethod]] = []
    for stream in sorted(video_file.streams):
        if isinstance(stream, AudioStream):
            conversion_method: ConversionMethod = EncodeAudio(codec="aac")
        else:
            conversion_method = Copy()
        file_conversion_plan.append(
            StreamConversionPlan(
                source_stream=stream,
                conversion_method=conversion_method,
            )
        )

    converted_file = ConvertedVideoFile[FileConversionPlan](
        path=ts_file,
        file_conversion_plan=FileConversionPlan(root=tuple(file_conversion_plan)),
    )

    # Act
    metrics_dict = await get_audio_quality_metrics(
        converted_file, SubprocessFFmpegRunner()
    )

    # Assert
    assert len(metrics_dict) == len(video_file.valid_audio_streams)
    for stream_index, metrics in metrics_dict.items():
        assert stream_index in [s.index for s in video_file.valid_audio_streams]
        assert metrics.apsnr
        assert metrics.asdr
        # APSNR and ASDR should be positive for identical files
        assert all(value > 0 for segment in metrics.apsnr for value in segment)
        assert all(value > 0 for segment in metrics.asdr for value in segment)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_reports_each_channel_layout_segment(
    tmp_path: Path, mixed_surround_ts_file: Path
) -> None:
    """Return one segment per channel layout for audio switching from stereo to 5.1ch."""
    # Arrange
    ffmpeg_runner = SubprocessFFmpegRunner()
    original_file = VideoFile(path=mixed_surround_ts_file)
    converted_file = execute_conversion(
        FileConversionPlan(
            root=(
                StreamConversionPlan(
                    source_stream=VideoStream(file=original_file, index=0),
                    conversion_method=Copy(),
                ),
                StreamConversionPlan(
                    source_stream=AudioStream(file=original_file, index=1),
                    conversion_method=EncodeAudio(
                        codec="aac",
                        channels=6,
                        audio_filter="aformat=channel_layouts=5.1",
                    ),
                ),
            )
        ),
        tmp_path / "converted.mp4",
        ffmpeg_runner,
    )

    # Act
    metrics_dict = await get_audio_quality_metrics(converted_file, ffmpeg_runner)

    # Assert
    assert len(metrics_dict[1].apsnr) >= 2
