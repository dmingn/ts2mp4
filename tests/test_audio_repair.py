from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_repair import (
    _build_ffmpeg_args,
    _get_audio_stream_codec,
    reencode_and_replace_audio_streams,
)
from ts2mp4.ffmpeg import FFmpegResult, execute_ffmpeg
from ts2mp4.ts2mp4 import ts2mp4


def test_build_ffmpeg_args(mocker: MockerFixture, tmp_path: Path) -> None:
    """
    Test the _build_ffmpeg_args helper function.

    This test case arranges a scenario where:
    - The input video has two audio streams.
    - The first audio stream (index 0) has failed the integrity check.
    - The second audio stream (index 1) has passed.

    The assertion checks whether the ffmpeg arguments are constructed correctly to:
    - Re-encode the failed stream (index 0) from the original TS file (input 1).
    - Copy the passed stream (index 1) from the intermediate MP4 file (input 0).
    """
    mocker.patch("ts2mp4.audio_repair._get_audio_stream_codec", return_value="aac")
    mocker.patch("ts2mp4.audio_integrity._get_audio_stream_count", return_value=2)
    mocker.patch(
        "ts2mp4.audio_integrity.execute_ffprobe",
        return_value=FFmpegResult(
            stdout=b'{"streams": [{"codec_type": "audio"}, {"codec_type": "audio"}]}',
            stderr="",
            returncode=0,
        ),
    )

    original_ts_file = tmp_path / "dummy.ts"
    output_mp4_file = tmp_path / "dummy.mp4"
    temp_output_file = output_mp4_file.with_suffix(".temp.mp4")
    failed_stream_indices = [0]

    ffmpeg_args = _build_ffmpeg_args(
        original_ts_file,
        output_mp4_file,
        failed_stream_indices,
        temp_output_file,
    )

    assert "-map" in ffmpeg_args
    assert "1:a:0" in ffmpeg_args  # Failed stream re-encoded from original
    assert "0:a:1" in ffmpeg_args  # Passed stream copied from intermediate


def test_reencode_and_replace_audio_streams(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test the reencode_and_replace_audio_streams function."""
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.audio_repair.execute_ffmpeg",
        return_value=FFmpegResult(stdout=b"", stderr="", returncode=0),
    )
    mocker.patch(
        "ts2mp4.audio_repair._build_ffmpeg_args", return_value=["-y", "dummy_args"]
    )

    original_ts_file = tmp_path / "dummy.ts"
    output_mp4_file = tmp_path / "dummy.mp4"
    temp_output_file = output_mp4_file.with_suffix(".temp.mp4")
    original_ts_file.touch()
    output_mp4_file.touch()
    temp_output_file.touch()
    failed_stream_indices = [0]

    reencode_and_replace_audio_streams(
        original_ts_file, output_mp4_file, failed_stream_indices
    )

    mock_execute_ffmpeg.assert_called_once_with(["-y", "dummy_args"])


def test_reencode_and_replace_audio_streams_no_failed_streams(
    mocker: MockerFixture,
) -> None:
    """Test that reencode_and_replace_audio_streams does nothing when no streams failed."""
    mock_execute_ffmpeg = mocker.patch("ts2mp4.audio_repair.execute_ffmpeg")

    original_ts_file = Path("dummy.ts")
    output_mp4_file = Path("dummy.mp4")
    failed_stream_indices: list[int] = []

    reencode_and_replace_audio_streams(
        original_ts_file, output_mp4_file, failed_stream_indices
    )

    mock_execute_ffmpeg.assert_not_called()


def test_get_audio_stream_codec(mocker: MockerFixture, ts_file: Path) -> None:
    """Test the _get_audio_stream_codec helper function."""
    mock_execute_ffprobe = mocker.patch("ts2mp4.audio_repair.execute_ffprobe")
    mock_execute_ffprobe.return_value = FFmpegResult(
        stdout=b'{"streams": [{"codec_name": "aac"}]}', stderr="", returncode=0
    )
    codec = _get_audio_stream_codec(ts_file, 0)
    assert codec == "aac"


def test_get_audio_stream_codec_failure(mocker: MockerFixture, ts_file: Path) -> None:
    """Test _get_audio_stream_codec with a non-zero return code."""
    mock_execute_ffprobe = mocker.patch("ts2mp4.audio_repair.execute_ffprobe")
    mock_execute_ffprobe.return_value = FFmpegResult(
        stdout=b"", stderr="ffprobe error", returncode=1
    )
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _get_audio_stream_codec(ts_file, 0)


def test_get_audio_stream_codec_with_real_video(ts_file: Path) -> None:
    """Test _get_audio_stream_codec with a real video file."""
    codec = _get_audio_stream_codec(ts_file, 0)
    assert codec == "aac"


def test_reencode_and_replace_audio_streams_with_real_video(
    tmp_path: Path, ts_file: Path
) -> None:
    """Test reencode_and_replace_audio_streams with a real video file."""
    output_mp4_file = tmp_path / "output.mp4"
    ts2mp4(ts_file, output_mp4_file, crf=23, preset="medium")
    assert output_mp4_file.exists()

    reencode_and_replace_audio_streams(
        original_ts_file=ts_file,
        output_mp4_file=output_mp4_file,
        failed_stream_indices=[0],
    )

    # Verify that the audio stream has been re-encoded
    ffmpeg_args = [
        "-i",
        str(output_mp4_file),
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
    ]
    result = execute_ffmpeg(ffmpeg_args)
    assert result.returncode == 0
