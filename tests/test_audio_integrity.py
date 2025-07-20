from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    _get_audio_stream_count,
    _get_audio_stream_md5,
    get_failed_audio_stream_indices_by_integrity_check,
)
from ts2mp4.ffmpeg import FFmpegResult


def test_get_audio_stream_count(ts_file: Path) -> None:
    """Test the _get_audio_stream_count helper function."""
    expected_stream_count = 1
    actual_stream_count = _get_audio_stream_count(ts_file)
    assert actual_stream_count == expected_stream_count


def test_get_audio_stream_md5(ts_file: Path) -> None:
    """Test the _get_audio_stream_md5 helper function."""
    expected_md5 = "9db9dd4cb46b9678894578946158955b"
    actual_md5 = _get_audio_stream_md5(ts_file, 0)
    assert actual_md5 == expected_md5


def test_get_failed_audio_stream_indices_by_integrity_check_matches(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5",
        side_effect=[
            "hash1_input",
            "hash1_input",
            "hash2_input",
            "hash2_input",
        ],
    )

    failed_streams = get_failed_audio_stream_indices_by_integrity_check(
        input_file, output_file
    )
    assert failed_streams == []


def test_get_failed_audio_stream_indices_by_integrity_check_mismatch(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5",
        side_effect=[
            "hash1_input",
            "hash1_output_mismatch",
            "hash2_input",
            "hash2_input",
        ],
    )

    failed_streams = get_failed_audio_stream_indices_by_integrity_check(
        input_file, output_file
    )
    assert failed_streams == [0]


def test_get_failed_audio_stream_indices_by_integrity_check_md5_generation_fails(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5",
        side_effect=[
            "hash1_input",
            RuntimeError("ffmpeg failed"),
            "hash2_input",
            "hash2_input",
        ],
    )

    failed_streams = get_failed_audio_stream_indices_by_integrity_check(
        input_file, output_file
    )
    assert failed_streams == [0]


def test_get_audio_stream_count_failure(mocker: MockerFixture, ts_file: Path) -> None:
    """Test _get_audio_stream_count with a non-zero return code."""
    mock_execute_ffprobe = mocker.patch("ts2mp4.audio_integrity.execute_ffprobe")
    mock_execute_ffprobe.return_value = FFmpegResult(
        stdout=b"", stderr="ffprobe error", returncode=1
    )
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _get_audio_stream_count(ts_file)


def test_get_audio_stream_md5_failure(mocker: MockerFixture, ts_file: Path) -> None:
    """Test _get_audio_stream_md5 with a non-zero return code."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.audio_integrity.execute_ffmpeg")
    mock_execute_ffmpeg.return_value = FFmpegResult(
        stdout=b"", stderr="ffmpeg error", returncode=1
    )
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        _get_audio_stream_md5(ts_file, 0)


def test_get_failed_audio_stream_indices_by_integrity_check_no_audio_streams(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=0)
    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_md5", return_value="")

    failed_streams = get_failed_audio_stream_indices_by_integrity_check(
        input_file, output_file
    )
    assert failed_streams == []
