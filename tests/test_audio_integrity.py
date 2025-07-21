from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    check_stream_integrity,
    re_encode_mismatched_audio_streams,
    verify_audio_stream_integrity,
)
from ts2mp4.media_info import MediaInfo, Stream


@pytest.mark.unit
def test_check_stream_integrity_matching_hashes(mocker: MockerFixture) -> None:
    """Tests that check_stream_integrity returns True when MD5 hashes match."""
    mocker.patch("ts2mp4.audio_integrity.get_stream_md5", return_value="same_hash")
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert check_stream_integrity(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_check_stream_integrity_mismatching_hashes(mocker: MockerFixture) -> None:
    """Tests that check_stream_integrity returns False when MD5 hashes mismatch."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert not check_stream_integrity(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_check_stream_integrity_hash_generation_fails(mocker: MockerFixture) -> None:
    """Tests that check_stream_integrity returns False when hash generation fails."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5", side_effect=RuntimeError("Mock error")
    )
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert not check_stream_integrity(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_verify_audio_stream_integrity_matches(mocker: MockerFixture) -> None:
    """Tests that no exception is raised when all stream hashes match."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
        ],
    )
    mock_check_stream_integrity = mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity", return_value=True
    )

    verify_audio_stream_integrity(input_file, output_file)

    mock_check_stream_integrity.assert_called_once()


@pytest.mark.unit
def test_verify_audio_stream_integrity_mismatch(mocker: MockerFixture) -> None:
    """Tests that a RuntimeError is raised when stream hashes mismatch."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
        ],
    )
    mock_check_stream_integrity = mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity", return_value=False
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_audio_stream_integrity(input_file, output_file)

    assert "Audio stream integrity check failed for stream at index 1" in str(
        excinfo.value
    )
    mock_check_stream_integrity.assert_called_once()


@pytest.mark.unit
def test_verify_audio_stream_integrity_stream_count_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that a RuntimeError is raised for mismatched audio stream counts."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
            MediaInfo(streams=(Stream(codec_type="video", index=0),)),
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_audio_stream_integrity(input_file, output_file)
    assert "Mismatch in the number of audio streams" in str(excinfo.value)


@pytest.mark.unit
def test_verify_audio_stream_integrity_no_audio_streams(mocker: MockerFixture) -> None:
    """Tests correct handling when there are no audio streams."""
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        return_value=MediaInfo(
            streams=(
                Stream(codec_type="video", index=0),
                Stream(codec_type="subtitle", index=1),
            )
        ),
    )
    mock_check_stream_integrity = mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity"
    )

    verify_audio_stream_integrity(input_file, output_file)

    mock_check_stream_integrity.assert_not_called()


@pytest.mark.unit
def test_re_encode_mismatched_audio_streams(mocker: MockerFixture) -> None:
    """Tests the re-encoding function call."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="aac"),
                    Stream(codec_type="audio", index=1, codec_name="ac3"),
                ]
            ),
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="aac"),
                    Stream(codec_type="audio", index=1, codec_name="ac3"),
                ]
            ),
        ],
    )
    mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity", side_effect=[True, False]
    )
    mock_execute_ffmpeg = mocker.patch(
        "ts2mp4.audio_integrity.execute_ffmpeg",
        return_value=CompletedProcess(args=[], returncode=0),
    )

    re_encode_mismatched_audio_streams(
        Path("original.ts"), Path("encoded.mp4"), Path("output.mp4")
    )

    mock_execute_ffmpeg.assert_called_once()
    ffmpeg_args = mock_execute_ffmpeg.call_args[0][0]
    assert "-codec:a:0" in ffmpeg_args
    assert "copy" in ffmpeg_args
    assert "-codec:a:1" in ffmpeg_args
    assert "ac3" in ffmpeg_args


@pytest.mark.unit
def test_re_encode_mismatched_audio_streams_no_args(mocker: MockerFixture) -> None:
    """Tests that ffmpeg is not called when no arguments are generated."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info", return_value=MediaInfo(streams=[])
    )
    mock_execute_ffmpeg = mocker.patch("ts2mp4.audio_integrity.execute_ffmpeg")

    re_encode_mismatched_audio_streams(
        Path("original.ts"), Path("encoded.mp4"), Path("output.mp4")
    )

    mock_execute_ffmpeg.assert_not_called()
