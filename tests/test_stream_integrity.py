"""Unit tests for the stream_integrity module."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.stream_integrity import compare_stream_hashes, verify_copied_streams
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


@pytest.fixture
def mock_converted_video_file(
    mocker: MockerFixture,
    mock_input_video_file: MagicMock,
    mock_output_video_file: MagicMock,
) -> MagicMock:
    """Return a mocked ConvertedVideoFile instance."""
    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = mock_output_video_file.path
    mock_converted_file.media_info = mock_output_video_file.media_info
    mock_converted_file.stream_sources = StreamSources(
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

    # MagicMock doesn't automatically handle properties that are generators
    type(mock_converted_file).stream_with_sources = mocker.PropertyMock(
        return_value=zip(
            mock_converted_file.media_info.streams, mock_converted_file.stream_sources
        )
    )

    return mock_converted_file


@pytest.mark.unit
@pytest.mark.parametrize("hashes_match", [True, False])
def test_verify_copied_streams(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
    hashes_match: bool,
) -> None:
    """Tests verify_copied_streams with matching and mismatching hashes."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes", return_value=hashes_match
    )

    if hashes_match:
        verify_copied_streams(mock_converted_video_file)
    else:
        with pytest.raises(RuntimeError) as excinfo:
            verify_copied_streams(mock_converted_video_file)
        assert "Audio stream integrity check failed for stream at index 1" in str(
            excinfo.value
        )

    mock_compare_stream_hashes.assert_called_once()


@pytest.mark.unit
def test_verify_copied_streams_no_copied_streams(
    mocker: MockerFixture, mock_converted_video_file: MagicMock
) -> None:
    """Tests that no checks are performed if there are no copied streams."""
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )
    stream_sources = list(mock_converted_video_file.stream_sources)
    stream_sources[1] = StreamSource(
        source_video_file=stream_sources[1].source_video_file,
        source_stream_index=1,
        conversion_type=ConversionType.CONVERTED,
    )
    mock_converted_video_file.stream_sources = StreamSources(stream_sources)

    type(mock_converted_video_file).stream_with_sources = mocker.PropertyMock(
        return_value=zip(
            mock_converted_video_file.media_info.streams,
            mock_converted_video_file.stream_sources,
        )
    )

    verify_copied_streams(mock_converted_video_file)

    mock_compare_stream_hashes.assert_not_called()


@pytest.mark.unit
def test_verify_copied_streams_unknown_stream_type(
    mocker: MockerFixture, mock_converted_video_file: MagicMock
) -> None:
    """Tests that a RuntimeError is raised with "Unknown" for a missing stream type."""
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)
    streams = list(mock_converted_video_file.media_info.streams)
    streams[1] = Stream(index=1, codec_type=None)
    mock_converted_video_file.media_info = MediaInfo(streams=tuple(streams))

    type(mock_converted_video_file).stream_with_sources = mocker.PropertyMock(
        return_value=zip(
            mock_converted_video_file.media_info.streams,
            mock_converted_video_file.stream_sources,
        )
    )

    with pytest.raises(RuntimeError) as excinfo:
        verify_copied_streams(mock_converted_video_file)

    assert "Unknown stream integrity check failed for stream at index 1" in str(
        excinfo.value
    )
