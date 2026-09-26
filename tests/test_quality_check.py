"""Unit and integration tests for the quality_check module."""

from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.quality_check import (
    AudioQualityMetrics,
    check_audio_quality,
    get_audio_quality_metrics,
    parse_audio_quality_metrics,
)
from ts2mp4.stream_source import (
    Conversion,
    ConvertedVideoFile,
    Copy,
    EncodeAudio,
    StreamSource,
    StreamSources,
    StreamWithSource,
)
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ffmpeg_output, expected_apsnr, expected_asdr",
    [
        (
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: inf dB\n[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: inf dB",
            float("inf"),
            float("inf"),
        ),
        ("[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: 30.00 dB", 30.00, None),
        ("[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: 25.00 dB", None, 25.00),
        ("No metrics here", None, None),
        ("[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: invalid dB", None, None),
        ("[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: invalid dB", None, None),
        ("[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: -10.50 dB", -10.50, None),
        ("[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: -5.25 dB", None, -5.25),
        ("[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch1: 42.0 dB", 42.0, None),
        ("[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch1: -nan dB", None, float("nan")),
        (
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 10.0 dB\n[Parsed_apsnr_0 @ 0x123] PSNR ch1: 20.0 dB",
            10.0,
            None,
        ),
    ],
)
async def test_parse_audio_quality_metrics(
    ffmpeg_output: str,
    expected_apsnr: float | None,
    expected_asdr: float | None,
) -> None:
    """Parse audio quality metrics from FFmpeg stderr lines."""

    # Arrange
    async def input_generator() -> AsyncGenerator[str, None]:
        for line in ffmpeg_output.splitlines():
            yield line

    # Act
    metrics = await parse_audio_quality_metrics(input_generator())

    # Assert
    assert metrics.apsnr == pytest.approx(expected_apsnr, nan_ok=True)
    assert metrics.asdr == pytest.approx(expected_asdr, nan_ok=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_metrics_for_encoded_audio(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Return APSNR/ASDR for each encoded audio stream and skip others."""
    # Arrange
    mock_stream = mocker.patch("ts2mp4.quality_check.execute_ffmpeg_stderr_streamed")

    async def mock_generator(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[str, None]:
        yield "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB"
        yield "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB"

    mock_stream.side_effect = mock_generator

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    stream2 = VideoStream(file=converted_video, index=1)
    stream3 = AudioStream(file=converted_video, index=2)

    source1: StreamSource[AudioStream, Conversion] = StreamSource(
        conversion=EncodeAudio(),
        source_stream=AudioStream(file=original_file, index=0),
    )
    source2: StreamSource[VideoStream, Conversion] = StreamSource(
        conversion=Copy(),
        source_stream=VideoStream(file=original_file, index=1),
    )
    source3: StreamSource[AudioStream, Conversion] = StreamSource(
        conversion=EncodeAudio(),
        source_stream=AudioStream(file=original_file, index=1),
    )

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.stream_with_sources = [
        StreamWithSource(stream=stream1, source=source1),
        StreamWithSource(stream=stream2, source=source2),
        StreamWithSource(stream=stream3, source=source3),
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file)

    # Assert
    assert len(metrics) == 2
    assert 0 in metrics
    assert 2 in metrics
    assert metrics[0] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert metrics[2] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert mock_stream.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_skips_failed_stream(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Omit a stream when FFmpeg fails and keep metrics for later streams."""
    # Arrange
    mock_stream = mocker.patch("ts2mp4.quality_check.execute_ffmpeg_stderr_streamed")

    async def mock_generator() -> AsyncGenerator[str, None]:
        yield "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB"
        yield "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB"

    mock_stream.side_effect = [
        FFmpegProcessError("Error"),
        mock_generator(),
    ]

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    stream2 = AudioStream(file=converted_video, index=2)

    source1: StreamSource[AudioStream, Conversion] = StreamSource(
        conversion=EncodeAudio(),
        source_stream=AudioStream(file=original_file, index=0),
    )
    source2: StreamSource[AudioStream, Conversion] = StreamSource(
        conversion=EncodeAudio(),
        source_stream=AudioStream(file=original_file, index=1),
    )

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.stream_with_sources = [
        StreamWithSource(stream=stream1, source=source1),
        StreamWithSource(stream=stream2, source=source2),
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file)

    # Assert
    assert len(metrics) == 1
    assert 2 in metrics
    assert metrics[2] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert mock_stream.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_empty_when_no_metrics_parsed(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Return an empty dict when FFmpeg output contains no parseable metrics."""
    # Arrange
    mock_stream = mocker.patch("ts2mp4.quality_check.execute_ffmpeg_stderr_streamed")

    async def mock_generator(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[str, None]:
        yield "No metrics here"

    mock_stream.side_effect = mock_generator

    dummy_file = tmp_path / "original.ts"
    dummy_file.touch()
    original_file = VideoFile(path=dummy_file)
    output_file = tmp_path / "converted.mp4"
    output_file.touch()
    converted_video = VideoFile(path=output_file)

    stream1 = AudioStream(file=converted_video, index=0)
    source1: StreamSource[AudioStream, Conversion] = StreamSource(
        conversion=EncodeAudio(),
        source_stream=AudioStream(file=original_file, index=0),
    )
    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.stream_with_sources = [
        StreamWithSource(stream=stream1, source=source1)
    ]
    mock_converted_file.path = output_file

    # Act
    metrics = await get_audio_quality_metrics(mock_converted_file)

    # Assert
    assert len(metrics) == 0


@pytest.mark.unit
def test_check_audio_quality(mocker: MockerFixture) -> None:
    """Test the synchronous wrapper for get_audio_quality_metrics."""
    # Arrange
    mock_async_func = mocker.patch("ts2mp4.quality_check.get_audio_quality_metrics")
    mock_converted_file = MagicMock(spec=ConvertedVideoFile)

    # Act
    check_audio_quality(mock_converted_file)

    # Assert
    mock_async_func.assert_called_once_with(mock_converted_file)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_audio_quality_metrics_returns_positive_metrics_for_real_file(
    ts_file: Path,
) -> None:
    """Return positive APSNR/ASDR for each valid audio stream of a real file."""
    # Arrange
    video_file = VideoFile(path=ts_file)
    stream_sources: list[StreamSource[Stream, Conversion]] = []
    for stream in sorted(video_file.streams):
        if isinstance(stream, AudioStream):
            conversion: Conversion = EncodeAudio()
        else:
            conversion = Copy()
        stream_sources.append(
            StreamSource(
                source_stream=stream,
                conversion=conversion,
            )
        )

    converted_file = ConvertedVideoFile[StreamSources](
        path=ts_file, stream_sources=StreamSources(root=tuple(stream_sources))
    )

    # Act
    metrics_dict = await get_audio_quality_metrics(converted_file)

    # Assert
    assert len(metrics_dict) == len(video_file.valid_audio_streams)
    for stream_index, metrics in metrics_dict.items():
        assert stream_index in [s.index for s in video_file.valid_audio_streams]
        assert metrics is not None
        assert metrics.apsnr is not None
        assert metrics.asdr is not None
        assert metrics.apsnr > 0  # APSNR should be positive for identical files
        assert metrics.asdr > 0  # ASDR should be positive for identical files
