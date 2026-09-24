"""Unit and integration tests for the ffprobe_schema module."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffprobe_schema import (
    FFprobeFormat,
    FFprobeOutput,
    FFprobeStream,
    _probe_file_cached,
    probe_file,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _probe_file_cached.cache_clear()


def _ffprobe_result(stdout: bytes) -> MagicMock:
    mock_result = MagicMock()
    mock_result.stdout = stdout
    return mock_result


def _minimal_ffprobe_stdout() -> bytes:
    return json.dumps(
        {
            "streams": [{"codec_type": "video", "index": 0}],
            "format": {"format_name": "mpegts"},
        }
    ).encode("utf-8")


@pytest.mark.unit
def test_probe_file_returns_cached_result_for_unchanged_file(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """probe_file reuses the cached FFprobeOutput when mtime and size are unchanged."""
    # Arrange
    probe_target = tmp_path / "input.ts"
    probe_target.touch()
    mock_execute_ffprobe = mocker.patch(
        "ts2mp4.ffprobe_schema.execute_ffprobe",
        return_value=_ffprobe_result(_minimal_ffprobe_stdout()),
    )

    # Act
    result1 = probe_file(probe_target)
    result2 = probe_file(probe_target)

    # Assert
    assert result1 is result2
    mock_execute_ffprobe.assert_called_once()


@pytest.mark.unit
def test_probe_file_reprobes_when_file_stat_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """probe_file calls ffprobe again when mtime or size changes."""
    # Arrange
    probe_target = tmp_path / "input.ts"
    probe_target.touch()
    mock_execute_ffprobe = mocker.patch(
        "ts2mp4.ffprobe_schema.execute_ffprobe",
        return_value=_ffprobe_result(_minimal_ffprobe_stdout()),
    )

    # Act
    result1 = probe_file(probe_target)
    # Prefer an explicit mtime over Path.touch(): on filesystems with 1s
    # mtime resolution, touch() in a fast test may leave mtime unchanged and
    # fail to bust the cache.
    os.utime(probe_target, (1_700_000_000, 1_700_000_000))
    result2 = probe_file(probe_target)

    # Assert
    assert result1 is not result2
    assert mock_execute_ffprobe.call_count == 2


@pytest.mark.integration
def test_probe_file_reads_real_ts_streams(ts_file: Path) -> None:
    """probe_file returns expected stream metadata for the fixture TS file."""
    # Act
    result = probe_file(ts_file)

    # Assert
    # AAC bit_rate and stream/format durations vary across ffmpeg versions.
    variable_fields_exclude = {
        "streams": {"__all__": {"bit_rate", "duration"}},
        "format": {"duration"},
    }
    expected = FFprobeOutput(
        streams=(
            FFprobeStream(
                codec_type="video",
                index=0,
                width=1280,
                height=720,
                codec_name="mpeg2video",
                profile="Main",
            ),
            FFprobeStream(
                codec_type="audio",
                index=1,
                codec_name="aac",
                profile="LC",
                channels=1,
                sample_rate=44100,
            ),
            FFprobeStream(
                codec_type="audio",
                index=2,
                codec_name="aac",
                profile="LC",
                channels=1,
                sample_rate=44100,
            ),
        ),
        format=FFprobeFormat(format_name="mpegts"),
    )
    assert result.model_dump(
        exclude=variable_fields_exclude  # type: ignore[arg-type]
    ) == expected.model_dump(
        exclude=variable_fields_exclude  # type: ignore[arg-type]
    )


@pytest.mark.integration
def test_probe_file_reports_positive_durations(ts_file: Path) -> None:
    """probe_file reports positive durations for the fixture TS file."""
    # Act
    result = probe_file(ts_file)

    # Assert
    assert result.format is not None
    assert result.format.duration is not None
    assert result.format.duration > 0
    assert all(
        stream.duration is not None and stream.duration > 0 for stream in result.streams
    )


@pytest.mark.integration
def test_probe_file_reports_positive_audio_bit_rates(ts_file: Path) -> None:
    """probe_file reports positive bit rates for audio streams in the fixture TS."""
    # Act
    result = probe_file(ts_file)

    # Assert
    assert all(
        stream.bit_rate is not None and stream.bit_rate > 0
        for stream in result.streams
        if stream.codec_type == "audio"
    )
