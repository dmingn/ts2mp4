"""Unit and integration tests for the quality_check module."""

from pathlib import Path
from typing import Union

import pytest
from pytest_mock import MockerFixture

from ts2mp4.quality_check import (
    AudioQualityMetrics,
    get_audio_quality_metrics,
    parse_audio_quality_metrics,
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
@pytest.mark.parametrize(
    "ffmpeg_stderr, expected_metrics",
    [
        (
            "[Parsed_apsnr_0 @ 0x123] PSNR ch0: 30.00 dB\n[Parsed_asdr_1 @ 0x456] SDR ch0: 25.00 dB",
            AudioQualityMetrics(apsnr=30.00, asdr=25.00),
        ),
        (
            "Some other ffmpeg output\n[Parsed_apsnr_0 @ 0x123] PSNR ch0: inf dB",
            AudioQualityMetrics(apsnr=float("inf"), asdr=None),
        ),
        (
            "Error: something went wrong",
            None,
        ),
    ],
)
def test_get_audio_quality_metrics_unit(
    mocker: MockerFixture,
    ffmpeg_stderr: str,
    expected_metrics: Union[AudioQualityMetrics, None],
) -> None:
    """Test the audio quality metrics calculation unit."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.quality_check.execute_ffmpeg")
    mock_execute_ffmpeg.return_value.returncode = 0 if expected_metrics else 1
    mock_execute_ffmpeg.return_value.stderr = ffmpeg_stderr

    metrics = get_audio_quality_metrics(
        original_file=Path("dummy_original.ts"),
        re_encoded_file=Path("dummy_re_encoded.mp4"),
        audio_stream_index=0,
    )

    assert metrics == expected_metrics


@pytest.mark.integration
@pytest.mark.parametrize("audio_stream_index", [0, 1])
def test_get_audio_quality_metrics_integration(
    ts_file: Path, audio_stream_index: int
) -> None:
    """Test get_audio_quality_metrics with a real video file."""
    metrics = get_audio_quality_metrics(
        original_file=ts_file,
        re_encoded_file=ts_file,
        audio_stream_index=audio_stream_index,
    )
    assert metrics is not None
    assert metrics.apsnr is not None
    assert metrics.asdr is not None
    assert metrics.apsnr > 0  # APSNR should be positive for identical files
    assert metrics.asdr > 0  # ASDR should be positive for identical files
