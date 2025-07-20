from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    _get_audio_stream_count,
    verify_audio_stream_integrity,
)


@pytest.mark.integration
def test_get_audio_stream_count(ts_file: Path) -> None:
    """Test the _get_audio_stream_count helper function."""
    expected_stream_count = 1
    actual_stream_count = _get_audio_stream_count(ts_file)
    assert actual_stream_count == expected_stream_count


@pytest.mark.unit
def test_verify_audio_stream_integrity_matches(mocker: MockerFixture) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            "hash1_input",
            "hash2_input",  # input_file のMD5
            "hash1_input",
            "hash2_input",  # output_file のMD5 (一致)
        ],
    )

    verify_audio_stream_integrity(input_file, output_file)


@pytest.mark.unit
def test_verify_audio_stream_integrity_mismatch(mocker: MockerFixture) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=1)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            "hash_input",  # input_file のMD5
            "hash_output",  # output_file のMD5 (不一致)
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_audio_stream_integrity(input_file, output_file)

    assert "Audio stream MD5 mismatch!" in str(excinfo.value)


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
def test_verify_audio_stream_integrity_no_audio_streams(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=0)
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5", return_value=""
    )  # 呼ばれないが念のため

    verify_audio_stream_integrity(input_file, output_file)
