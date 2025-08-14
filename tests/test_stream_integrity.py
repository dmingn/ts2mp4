"""Unit tests for the stream_integrity module."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.stream_integrity import (
    compare_stream_hashes,
    verify_copied_streams,
    verify_streams,
)
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    VideoFile,
)


@pytest.fixture
def mock_input_video_file(mocker: MockerFixture) -> MagicMock:
    """Return a mocked input VideoFile instance."""
    mock_input = cast(MagicMock, mocker.MagicMock(spec=VideoFile))
    mock_input.path = Path("dummy_input.ts")
    # Set default media_info for input, can be overridden in tests if needed
    mock_input.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    return mock_input


@pytest.fixture
def mock_output_video_file(mocker: MockerFixture) -> MagicMock:
    """Return a mocked output VideoFile instance."""
    mock_output = cast(MagicMock, mocker.MagicMock(spec=VideoFile))
    mock_output.path = Path("dummy_output.mp4.part")
    # Set default media_info for output, can be overridden in tests if needed
    mock_output.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    return mock_output


@pytest.mark.unit
def test_compare_stream_hashes_matching_hashes(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that compare_stream_hashes returns True when MD5 hashes match."""
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash")

    stream = Stream(codec_type="audio", index=1)

    assert compare_stream_hashes(
        input_video=mock_input_video_file,
        output_video=mock_output_video_file,
        input_stream=stream,
        output_stream=stream,
    )


@pytest.mark.unit
def test_compare_stream_hashes_mismatching_hashes(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that compare_stream_hashes returns False when MD5 hashes mismatch."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )
    stream = Stream(codec_type="audio", index=1)

    assert not compare_stream_hashes(
        input_video=mock_input_video_file,
        output_video=mock_output_video_file,
        input_stream=stream,
        output_stream=stream,
    )


@pytest.mark.unit
def test_compare_stream_hashes_hash_generation_fails(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that compare_stream_hashes returns False when hash generation fails."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5",
        side_effect=RuntimeError("Mock error"),
    )
    stream = Stream(codec_type="audio", index=1)

    assert not compare_stream_hashes(
        input_video=mock_input_video_file,
        output_video=mock_output_video_file,
        input_stream=stream,
        output_stream=stream,
    )


@pytest.mark.unit
def test_verify_streams_matches(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that no exception is raised when all stream hashes match."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    verify_streams(mock_input_video_file, mock_output_video_file, "audio")

    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_streams_mismatch(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that a RuntimeError is raised when stream hashes mismatch."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=False
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_streams(mock_input_video_file, mock_output_video_file, "audio")

    assert "Audio stream integrity check failed for stream at index 1" in str(
        excinfo.value
    )
    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_streams_stream_count_mismatch(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that a RuntimeError is raised for mismatched audio stream counts."""
    # Override media_info for this specific test case
    mock_input_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    mock_output_video_file.media_info = MediaInfo(
        streams=(Stream(codec_type="video", index=0),)
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_streams(mock_input_video_file, mock_output_video_file, "audio")
    assert "Mismatch in the number of audio streams" in str(excinfo.value)


@pytest.mark.unit
def test_verify_streams_no_audio_streams(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests correct handling when there are no audio streams."""
    # Override media_info for this specific test case
    mock_input_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="subtitle", index=1),
        )
    )
    mock_output_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="subtitle", index=1),
        )
    )

    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )

    verify_streams(mock_input_video_file, mock_output_video_file, "audio")

    mock_compare_stream_hashes.assert_not_called()


@pytest.mark.unit
def test_verify_streams_specific_indices(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that verify_streams correctly checks specific stream indices."""
    # Override media_info for this specific test case
    mock_input_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="audio", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    mock_output_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="audio", index=0),
            Stream(codec_type="audio", index=1),
        )
    )

    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    verify_streams(
        mock_input_video_file,
        mock_output_video_file,
        "audio",
        type_specific_stream_indices=[1],
    )

    # Ensures that only the stream at index 1 is checked
    assert mock_compare_stream_hashes.call_count == 1
    checked_stream = mock_compare_stream_hashes.call_args.kwargs["input_stream"]
    assert checked_stream.index == 1


@pytest.mark.unit
def test_verify_streams_video_mismatch(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> None:
    """Tests that a RuntimeError is raised for video stream mismatch."""
    # Override media_info for this specific test case
    mock_input_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    mock_output_video_file.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )

    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)

    with pytest.raises(RuntimeError) as excinfo:
        verify_streams(mock_input_video_file, mock_output_video_file, "video")

    assert "Video stream integrity check failed for stream at index 0" in str(
        excinfo.value
    )


@pytest.fixture
def mock_converted_video_file(
    mocker: MockerFixture, mock_input_video_file: MagicMock
) -> MagicMock:
    """Return a mocked ConvertedVideoFile instance."""
    mock_output = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_output.path = Path("dummy_output.mp4.part")
    mock_output.media_info = MediaInfo(
        streams=(
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        )
    )
    mock_output.stream_sources = StreamSources(
        [
            StreamSource(
                source_video_file=mock_input_video_file,
                source_stream_index=0,
                conversion_type=ConversionType.CONVERTED,
            ),
            StreamSource(
                source_video_file=mock_input_video_file,
                source_stream_index=1,
                conversion_type=ConversionType.COPIED,
            ),
        ]
    )
    return mock_output


@pytest.mark.unit
def test_verify_copied_streams_matches(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """Tests that no exception is raised when all copied stream hashes match."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=True
    )

    verify_copied_streams(mock_converted_video_file)

    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_copied_streams_mismatch(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """Tests that a RuntimeError is raised when a copied stream hash mismatches."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=False
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_copied_streams(mock_converted_video_file)

    assert "Audio stream integrity check failed for stream at index 1" in str(
        excinfo.value
    )
    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_copied_streams_no_copied_streams(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """Tests that no checks are performed if there are no copied streams."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )
    mock_converted_video_file.stream_sources = StreamSources(
        [
            s
            for s in mock_converted_video_file.stream_sources
            if s.conversion_type != ConversionType.COPIED
        ]
    )

    verify_copied_streams(mock_converted_video_file)

    mock_compare_stream_hashes.assert_not_called()
