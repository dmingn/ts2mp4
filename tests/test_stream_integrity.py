"""Unit tests for the stream_integrity module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.stream_integrity import compare_stream_hashes, verify_streams


@pytest.mark.unit
def test_compare_stream_hashes_matching_hashes(mocker: MockerFixture) -> None:
    """Tests that compare_stream_hashes returns True when MD5 hashes match."""
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash")
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert compare_stream_hashes(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_compare_stream_hashes_mismatching_hashes(mocker: MockerFixture) -> None:
    """Tests that compare_stream_hashes returns False when MD5 hashes mismatch."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert not compare_stream_hashes(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_compare_stream_hashes_hash_generation_fails(mocker: MockerFixture) -> None:
    """Tests that compare_stream_hashes returns False when hash generation fails."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5",
        side_effect=RuntimeError("Mock error"),
    )
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")
    stream = Stream(codec_type="audio", index=1)

    assert not compare_stream_hashes(input_file, output_file, stream, stream)


@pytest.mark.unit
def test_verify_streams_matches(mocker: MockerFixture) -> None:
    """Tests that no exception is raised when all stream hashes match."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
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
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    verify_streams(input_file, output_file, "audio")

    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_streams_mismatch(mocker: MockerFixture) -> None:
    """Tests that a RuntimeError is raised when stream hashes mismatch."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
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
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=False
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_streams(input_file, output_file, "audio")

    assert "Audio stream integrity check failed for stream at index 1" in str(
        excinfo.value
    )
    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_streams_stream_count_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that a RuntimeError is raised for mismatched audio stream counts."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
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
        verify_streams(input_file, output_file, "audio")
    assert "Mismatch in the number of audio streams" in str(excinfo.value)


@pytest.mark.unit
def test_verify_streams_no_audio_streams(mocker: MockerFixture) -> None:
    """Tests correct handling when there are no audio streams."""
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        return_value=MediaInfo(
            streams=(
                Stream(codec_type="video", index=0),
                Stream(codec_type="subtitle", index=1),
            )
        ),
    )
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )

    verify_streams(input_file, output_file, "audio")

    mock_compare_stream_hashes.assert_not_called()


@pytest.mark.unit
def test_verify_streams_specific_indices(mocker: MockerFixture) -> None:
    """Tests that verify_streams correctly checks specific stream indices."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        side_effect=[
            MediaInfo(
                streams=(
                    Stream(codec_type="audio", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
            MediaInfo(
                streams=(
                    Stream(codec_type="audio", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),
        ],
    )
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    verify_streams(input_file, output_file, "audio", type_specific_stream_indices=[1])

    # Ensures that only the stream at index 1 is checked
    assert mock_compare_stream_hashes.call_count == 1
    checked_stream = mock_compare_stream_hashes.call_args[0][2]
    assert checked_stream.index == 1


@pytest.mark.unit
def test_verify_streams_video_mismatch(mocker: MockerFixture) -> None:
    """Tests that a RuntimeError is raised for video stream mismatch."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
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
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)

    with pytest.raises(RuntimeError) as excinfo:
        verify_streams(input_file, output_file, "video")

    assert "Video stream integrity check failed for stream at index 0" in str(
        excinfo.value
    )
