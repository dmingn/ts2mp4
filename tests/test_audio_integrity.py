from pathlib import Path
from typing import Union

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_integrity import get_mismatched_audio_stream_indices
from ts2mp4.media_info import MediaInfo, Stream


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_matches(mocker: MockerFixture) -> None:
    """Tests that an empty list is returned when all stream hashes match."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    common_streams = (
        Stream(codec_type="video", index=0),
        Stream(codec_type="audio", index=1),
        Stream(codec_type="audio", index=2),
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=common_streams),  # MediaInfo for input_file
            MediaInfo(streams=common_streams),  # MediaInfo for output_file
        ],
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            "stream_1_hash",  # For input_file, stream_index=1
            "stream_1_hash",  # For output_file, stream_index=1
            "stream_2_hash",  # For input_file, stream_index=2
            "stream_2_hash",  # For output_file, stream_index=2
        ],
    )

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == []


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_mismatch(mocker: MockerFixture) -> None:
    """Tests that a list of mismatched indices is returned correctly."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    common_streams = (
        Stream(codec_type="video", index=0),
        Stream(codec_type="audio", index=1),
        Stream(codec_type="audio", index=2),
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=common_streams),  # MediaInfo for input_file
            MediaInfo(streams=common_streams),  # MediaInfo for output_file
        ],
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_stream_md5",
        side_effect=[
            "stream_1_input_hash",  # For input_file, stream_index=1
            "stream_1_output_hash_mismatch",  # For output_file, stream_index=1
            "stream_2_hash",  # For input_file, stream_index=2
            "stream_2_hash",  # For output_file, stream_index=2
        ],
    )

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == [(1, 1)]  # Index of the mismatched audio stream


@pytest.mark.unit
@pytest.mark.parametrize(
    "md5_side_effect, expected_result",
    [
        pytest.param(
            [
                "stream_1_input_hash",
                RuntimeError("ffmpeg error: stream 1 output hash failed"),
                "stream_2_hash",
                "stream_2_hash",
                "stream_3_hash",
                "stream_3_hash",
            ],
            [(1, 1)],
            id="output_hash_failure",
        ),
        pytest.param(
            [
                "stream_1_hash",
                "stream_1_hash",
                RuntimeError("ffmpeg error: stream 2 input hash failed"),
                "stream_3_hash",
                "stream_3_hash",
            ],
            [(2, 2)],
            id="input_hash_failure",
        ),
        pytest.param(
            [
                "stream_1_input_ok",
                RuntimeError("ffmpeg error: stream 1 output failed"),
                RuntimeError("ffmpeg error: stream 2 input failed"),
                "stream_3_input_ok",
                RuntimeError("ffmpeg error: stream 3 output failed"),
            ],
            [(1, 1), (2, 2), (3, 3)],
            id="multiple_hash_failures",
        ),
    ],
)
def test_get_mismatched_audio_stream_indices_hash_failure(
    mocker: MockerFixture,
    md5_side_effect: Union[list[str], list[RuntimeError]],
    expected_result: list[Union[tuple[int, int], tuple[int, None], tuple[None, int]]],
) -> None:
    """Tests that indices with hash generation failures are reported."""
    input_file = Path("dummy_input.ts")
    output_file = Path("dummy_output.mp4.part")

    common_streams = (
        Stream(codec_type="video", index=0),
        Stream(codec_type="audio", index=1),
        Stream(codec_type="audio", index=2),
        Stream(codec_type="audio", index=3),
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=common_streams),  # MediaInfo for input_file
            MediaInfo(streams=common_streams),  # MediaInfo for output_file
        ],
    )

    mocker.patch("ts2mp4.audio_integrity.get_stream_md5", side_effect=md5_side_effect)

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == expected_result


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_no_audio_streams(
    mocker: MockerFixture,
) -> None:
    """Tests correct handling when there are no audio streams."""
    input_file = Path("dummy_input_no_audio.ts")
    output_file = Path("dummy_output_no_audio.mp4.part")

    no_audio_streams = (
        Stream(codec_type="video", index=0),
        Stream(codec_type="subtitle", index=1),
    )

    mocker.patch(
        "ts2mp4.audio_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=no_audio_streams),
            MediaInfo(streams=no_audio_streams),
        ],
    )
    mock_get_stream_md5 = mocker.patch("ts2mp4.audio_integrity.get_stream_md5")

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == []
    mock_get_stream_md5.assert_not_called()


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_missing_output_stream(
    mocker: MockerFixture,
) -> None:
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
    mock_get_stream_md5 = mocker.patch("ts2mp4.audio_integrity.get_stream_md5")

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == [(1, None)]
    mock_get_stream_md5.assert_not_called()


@pytest.mark.unit
def test_get_mismatched_audio_stream_indices_output_stream_type_mismatch(
    mocker: MockerFixture,
) -> None:
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
                    Stream(codec_type="subtitle", index=1),
                )
            ),
        ],
    )
    mock_get_stream_md5 = mocker.patch("ts2mp4.audio_integrity.get_stream_md5")

    result = get_mismatched_audio_stream_indices(input_file, output_file)
    assert result == [(1, None)]
    mock_get_stream_md5.assert_not_called()
