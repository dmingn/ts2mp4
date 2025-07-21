from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import (
    _build_args_for_audio_streams,
    _build_re_encode_args,
    _verify_re_encoded_stream_integrity,
    check_stream_integrity,
    re_encode_mismatched_audio_streams,
    verify_audio_stream_integrity,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.media_info import MediaInfo, Stream, get_media_info


@pytest.mark.unit
def test_build_re_encode_args() -> None:
    stream = Stream(
        index=1,
        codec_name="aac",
        codec_type="audio",
        sample_rate=48000,
        channels=2,
        profile="LC",
        bit_rate=192000,
    )
    args = _build_re_encode_args(1, stream)
    assert args == [
        "-map",
        "0:a:1",
        "-codec:a:1",
        "aac",
        "-ar:a:1",
        "48000",
        "-ac:a:1",
        "2",
        "-profile:a:1",
        "aac_low",
        "-b:a:1",
        "192000",
        "-bsf:a:1",
        "aac_adtstoasc",
    ]


@pytest.mark.unit
def test_build_re_encode_args_with_none_values() -> None:
    stream = Stream(index=1, codec_name="aac", codec_type="audio")
    args = _build_re_encode_args(1, stream)
    assert args == ["-map", "0:a:1", "-codec:a:1", "aac", "-bsf:a:1", "aac_adtstoasc"]


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
def test_build_args_for_audio_streams_no_mismatch(mocker: MockerFixture) -> None:
    """Tests that copy arguments are generated when streams match."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        return_value=MediaInfo(
            streams=[
                Stream(codec_type="audio", index=0, codec_name="aac"),
                Stream(codec_type="audio", index=1, codec_name="mp3"),
            ]
        ),
    )
    mocker.patch("ts2mp4.audio_integrity.check_stream_integrity", return_value=True)

    result = _build_args_for_audio_streams(Path("original.ts"), Path("encoded.mp4"))
    assert result.ffmpeg_args == [
        "-map",
        "1:a:0",
        "-codec:a:0",
        "copy",
        "-map",
        "1:a:1",
        "-codec:a:1",
        "copy",
    ]
    assert result.copied_audio_stream_indices == [0, 1]


@pytest.mark.unit
def test_build_args_for_audio_streams_with_mismatch(mocker: MockerFixture) -> None:
    """Tests that re-encode arguments are generated for mismatched streams."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="aac"),
                    Stream(codec_type="audio", index=1, codec_name="aac"),
                ]
            ),
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="aac"),
                    Stream(codec_type="audio", index=1, codec_name="aac"),
                ]
            ),
        ],
    )
    mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity", side_effect=[True, False]
    )

    result = _build_args_for_audio_streams(Path("original.ts"), Path("encoded.mp4"))
    assert result.ffmpeg_args == [
        "-map",
        "1:a:0",
        "-codec:a:0",
        "copy",
        "-map",
        "0:a:1",
        "-codec:a:1",
        "aac",
        "-bsf:a:1",
        "aac_adtstoasc",
    ]
    assert result.copied_audio_stream_indices == [0]


@pytest.mark.unit
def test_build_args_for_audio_streams_unsupported_codec(
    mocker: MockerFixture,
) -> None:
    """Tests that a NotImplementedError is raised for unsupported codecs."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="mp3"),
                ]
            ),
            MediaInfo(
                streams=[
                    Stream(codec_type="audio", index=0, codec_name="mp3"),
                ]
            ),
        ],
    )
    mocker.patch("ts2mp4.audio_integrity.check_stream_integrity", return_value=False)

    with pytest.raises(NotImplementedError):
        _build_args_for_audio_streams(Path("original.ts"), Path("encoded.mp4"))


@pytest.mark.unit
def test_verify_re_encoded_stream_integrity_success(mocker: MockerFixture) -> None:
    """Tests that _verify_re_encoded_stream_integrity succeeds when all hashes match."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        return_value=MediaInfo(
            streams=[
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1),
            ]
        ),
    )
    mocker.patch("ts2mp4.audio_integrity.check_stream_integrity", return_value=True)
    _verify_re_encoded_stream_integrity(
        encoded_file=Path("encoded.mp4"),
        output_file=Path("output.mp4"),
        copied_audio_stream_indices=[0],
    )


@pytest.mark.unit
def test_verify_re_encoded_stream_integrity_video_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that _verify_re_encoded_stream_integrity fails on video hash mismatch."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        return_value=MediaInfo(
            streams=[
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1),
            ]
        ),
    )
    mocker.patch("ts2mp4.audio_integrity.check_stream_integrity", return_value=False)
    with pytest.raises(RuntimeError, match="Video stream integrity check failed"):
        _verify_re_encoded_stream_integrity(
            encoded_file=Path("encoded.mp4"),
            output_file=Path("output.mp4"),
            copied_audio_stream_indices=[0],
        )


@pytest.mark.unit
def test_verify_re_encoded_stream_integrity_audio_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that _verify_re_encoded_stream_integrity fails on audio hash mismatch."""
    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        return_value=MediaInfo(
            streams=[
                Stream(codec_type="video", index=0),
                Stream(codec_type="audio", index=1),
            ]
        ),
    )
    mocker.patch(
        "ts2mp4.audio_integrity.check_stream_integrity", side_effect=[True, False]
    )
    with pytest.raises(
        RuntimeError, match="Copied audio stream integrity check failed"
    ):
        _verify_re_encoded_stream_integrity(
            encoded_file=Path("encoded.mp4"),
            output_file=Path("output.mp4"),
            copied_audio_stream_indices=[0],
        )


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams_integration(
    tmp_path: Path, ts_file: Path
) -> None:
    """Tests the re-encoding function with a real video file."""
    # 1. Create a version of the test video with one audio stream removed
    encoded_file_with_missing_stream = tmp_path / "encoded_missing_stream.mp4"
    ffmpeg_args_remove_stream = [
        "-i",
        str(ts_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-codec",
        "copy",
        str(encoded_file_with_missing_stream),
    ]
    execute_ffmpeg(ffmpeg_args_remove_stream)

    # 2. Run the re-encoding function
    output_file = tmp_path / "output.mp4"
    re_encode_mismatched_audio_streams(
        original_file=ts_file,
        encoded_file=encoded_file_with_missing_stream,
        output_file=output_file,
    )

    # 3. Verify the output file
    output_media_info = get_media_info(output_file)
    original_media_info = get_media_info(ts_file)

    assert len(output_media_info.streams) == len(original_media_info.streams)
    # Further checks could be added here, e.g., comparing stream MD5s
