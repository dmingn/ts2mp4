from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    _get_audio_stream_count,
    get_mismatched_audio_stream_indices,
)


@pytest.mark.integration
def test_get_audio_stream_count(ts_file: Path) -> None:
    """Test the _get_audio_stream_count helper function."""
    expected_stream_count = 1
    actual_stream_count = _get_audio_stream_count(ts_file)
    assert actual_stream_count == expected_stream_count


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_matches(mocker: MockerFixture) -> None:
    """Tests that an empty list is returned when all stream hashes match."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            # Stream 0: Match
            "stream_0_hash",
            "stream_0_hash",
            # Stream 1: Match
            "stream_1_hash",
            "stream_1_hash",
        ],
    )

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == []


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_mismatch(mocker: MockerFixture) -> None:
    """Tests that a list of mismatched indices is returned correctly."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=3)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            # Stream 0: Match
            "stream_0_hash",
            "stream_0_hash",
            # Stream 1: Mismatch
            "stream_1_input_hash",
            "stream_1_output_hash_mismatch",
            # Stream 2: Match
            "stream_2_hash",
            "stream_2_hash",
        ],
    )

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == [1]


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_hash_failure(
    mocker: MockerFixture,
) -> None:
    """Tests that indices with hash generation failures are reported."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=4)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            # Stream 0: Match
            "stream_0_hash",
            "stream_0_hash",
            # Stream 1: Output hash fails
            "stream_1_input_hash",
            RuntimeError("ffmpeg error: stream 1 output hash failed"),
            # Stream 2: Input hash fails
            RuntimeError("ffmpeg error: stream 2 input hash failed"),
            "stream_2_output_hash_dummy",  # This won't be reached
            # Stream 3: Both hashes fail (input fails first)
            RuntimeError("ffmpeg error: stream 3 input hash failed"),
            "stream_3_output_hash_dummy",  # This won't be reached
        ],
    )

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == [1, 2, 3]


@pytest.mark.unit
def test_get_audio_stream_count_failure(mocker: MockerFixture, ts_file: Path) -> None:
    """Test _get_audio_stream_count with a non-zero return code."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=RuntimeError("ffprobe failed"),
    )
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _get_audio_stream_count(ts_file)


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_no_audio_streams(
    mocker: MockerFixture,
) -> None:
    """Tests correct handling when there are no audio streams."""
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=0)
    mocker.patch("ts2mp4.audio_integrity.get_stream_md5", return_value="")

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == []
