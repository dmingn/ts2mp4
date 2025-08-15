"""Unit and integration tests for the quality_check module."""

from pathlib import Path
from typing import Union
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.quality_check import (
    AudioQualityMetrics,
    get_audio_quality_metrics,
    parse_audio_quality_metrics,
)
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "ffmpeg_output, expected_apsnr, expected_asdr",
    [
        (
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: inf dB\n[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: inf dB",
            float("inf"),
            float("inf"),
        ),
        (
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: 30.00 dB",
            30.00,
            None,
        ),
        (
            "[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: 25.00 dB",
            None,
            25.00,
        ),
        (
            "No metrics here",
            None,
            None,
        ),
        (
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: invalid dB",
            None,
            None,
        ),
        (
            "[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: invalid dB",
            None,
            None,
        ),
        (
            "[Parsed_apsnr_0 @ 0x7f9990004800] PSNR ch0: -10.50 dB",
            -10.50,
            None,
        ),
        (
            "[Parsed_asdr_1 @ 0x7f9990004ac0] SDR ch0: -5.25 dB",
            None,
            -5.25,
        ),
    ],
)
def test_parse_audio_quality_metrics(
    ffmpeg_output: str,
    expected_apsnr: Union[float, None],
    expected_asdr: Union[float, None],
) -> None:
    """Test parsing of audio quality metrics from FFmpeg output."""
    metrics = parse_audio_quality_metrics(ffmpeg_output)
    assert metrics.apsnr == expected_apsnr
    assert metrics.asdr == expected_asdr


@pytest.mark.unit
def test_get_audio_quality_metrics_unit(mocker: MockerFixture) -> None:
    """Test the audio quality metrics calculation unit."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.quality_check.execute_ffmpeg")
    mock_execute_ffmpeg.return_value.returncode = 0
    mock_execute_ffmpeg.return_value.stderr = (
        "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB\n"
        "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB"
    )

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_stream1 = MagicMock(index=0, codec_type="audio")
    mock_stream2 = MagicMock(index=1, codec_type="video")
    mock_stream3 = MagicMock(index=2, codec_type="audio")

    mock_source1 = MagicMock(
        conversion_type=ConversionType.CONVERTED,
        source_stream=MagicMock(index=0),
        source_video_file=MagicMock(path="original.ts"),
    )
    mock_source2 = MagicMock(conversion_type=ConversionType.COPIED)
    mock_source3 = MagicMock(
        conversion_type=ConversionType.CONVERTED,
        source_stream=MagicMock(index=1),
        source_video_file=MagicMock(path="original.ts"),
    )

    mock_converted_file.stream_with_sources = [
        (mock_stream1, mock_source1),
        (mock_stream2, mock_source2),
        (mock_stream3, mock_source3),
    ]
    mock_converted_file.path = "converted.mp4"

    metrics = get_audio_quality_metrics(mock_converted_file)

    assert len(metrics) == 2
    assert 0 in metrics
    assert 2 in metrics
    assert metrics[0] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert metrics[2] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert mock_execute_ffmpeg.call_count == 2


@pytest.mark.unit
def test_get_audio_quality_metrics_partial_failure(mocker: MockerFixture) -> None:
    """Test quality metrics calculation with a partial FFmpeg failure."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.quality_check.execute_ffmpeg")

    # Simulate failure for the first call, success for the second
    mock_result_fail = MagicMock(returncode=1, stderr="Error")
    mock_result_success = MagicMock(
        returncode=0,
        stderr=(
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB\n"
            "[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB"
        ),
    )
    mock_execute_ffmpeg.side_effect = [mock_result_fail, mock_result_success]

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_stream1 = MagicMock(index=0, codec_type="audio")
    mock_stream2 = MagicMock(index=2, codec_type="audio")

    mock_source1 = MagicMock(
        conversion_type=ConversionType.CONVERTED,
        source_stream=MagicMock(index=0),
        source_video_file=MagicMock(path="original.ts"),
    )
    mock_source2 = MagicMock(
        conversion_type=ConversionType.CONVERTED,
        source_stream=MagicMock(index=1),
        source_video_file=MagicMock(path="original.ts"),
    )

    mock_converted_file.stream_with_sources = [
        (mock_stream1, mock_source1),
        (mock_stream2, mock_source2),
    ]
    mock_converted_file.path = "converted.mp4"

    metrics = get_audio_quality_metrics(mock_converted_file)

    assert len(metrics) == 1
    assert 2 in metrics
    assert metrics[2] == AudioQualityMetrics(apsnr=30.00, asdr=25.00)
    assert mock_execute_ffmpeg.call_count == 2


@pytest.mark.unit
def test_get_audio_quality_metrics_no_metrics_parsed(mocker: MockerFixture) -> None:
    """Test quality metrics calculation when no metrics are parsed from output."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.quality_check.execute_ffmpeg")
    mock_execute_ffmpeg.return_value.returncode = 0
    mock_execute_ffmpeg.return_value.stderr = "No metrics here"

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_stream1 = MagicMock(index=0, codec_type="audio")
    mock_source1 = MagicMock(
        conversion_type=ConversionType.CONVERTED,
        source_stream=MagicMock(index=0),
        source_video_file=MagicMock(path="original.ts"),
    )
    mock_converted_file.stream_with_sources = [(mock_stream1, mock_source1)]
    mock_converted_file.path = "converted.mp4"

    metrics = get_audio_quality_metrics(mock_converted_file)

    assert len(metrics) == 0


@pytest.mark.integration
def test_get_audio_quality_metrics_integration(ts_file: Path) -> None:
    """Test get_audio_quality_metrics with a real video file."""
    video_file = VideoFile(path=ts_file)
    stream_sources = []
    for stream in video_file.media_info.streams:
        stream_sources.append(
            StreamSource(
                source_video_file=video_file,
                source_stream_index=stream.index,
                conversion_type=(
                    ConversionType.CONVERTED
                    if stream.codec_type == "audio"
                    else ConversionType.COPIED
                ),
            )
        )

    converted_file = ConvertedVideoFile(
        path=ts_file, stream_sources=StreamSources(stream_sources)
    )

    metrics_dict = get_audio_quality_metrics(converted_file)

    assert len(metrics_dict) == len(video_file.valid_audio_streams)
    for stream_index, metrics in metrics_dict.items():
        assert stream_index in [s.index for s in video_file.valid_audio_streams]
        assert metrics is not None
        assert metrics.apsnr is not None
        assert metrics.asdr is not None
        assert metrics.apsnr > 0  # APSNR should be positive for identical files
        assert metrics.asdr > 0  # ASDR should be positive for identical files
