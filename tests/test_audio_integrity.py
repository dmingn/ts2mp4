from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    _get_audio_stream_count,
    _get_audio_stream_md5,
    verify_audio_stream_integrity,
)


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


def test_verify_audio_stream_integrity_matches(mocker: MockerFixture) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5",
        side_effect=[
            "hash1_input",
            "hash2_input",  # input_file のMD5
            "hash1_input",
            "hash2_input",  # output_file のMD5 (一致)
        ],
    )

    verify_audio_stream_integrity(input_file, output_file)


def test_verify_audio_stream_integrity_mismatch(mocker: MockerFixture) -> None:
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=1)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5",
        side_effect=[
            "hash_input",  # input_file のMD5
            "hash_output",  # output_file のMD5 (不一致)
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_audio_stream_integrity(input_file, output_file)

    assert "Audio stream MD5 mismatch!" in str(excinfo.value)


def test_verify_audio_stream_integrity_no_audio_streams(
    mocker: MockerFixture,
) -> None:
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=0)
    mocker.patch(
        "ts2mp4.audio_integrity._get_audio_stream_md5", return_value=""
    )  # 呼ばれないが念のため

    verify_audio_stream_integrity(input_file, output_file)
