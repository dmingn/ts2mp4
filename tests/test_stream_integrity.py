"""Unit tests for the stream_integrity module."""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.stream_integrity import StreamIntegrityError, verify_streams
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


@pytest.mark.unit
def test_verify_streams_no_copied_streams(
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that verify_streams does nothing if there are no COPIED streams."""
    mock_get_md5 = mocker.patch("ts2mp4.stream_integrity.get_stream_md5")
    converted_file = (
        converted_video_file_factory()
    )  # All streams are CONVERTED by default
    verify_streams(converted_file)
    mock_get_md5.assert_not_called()


@pytest.mark.unit
def test_verify_streams_success(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that verify_streams succeeds when hashes of copied streams match."""
    mock_get_md5 = mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash"
    )
    source_file = video_file_factory(
        streams=[
            Stream(codec_type="video", index=0),
            Stream(codec_type="audio", index=1),
        ]
    )
    converted_file = converted_video_file_factory(
        source_video_file=source_file,
        stream_sources={
            0: StreamSource(
                source_video_file=source_file,
                source_stream_index=0,
                conversion_type=ConversionType.CONVERTED,
            ),
            1: StreamSource(
                source_video_file=source_file,
                source_stream_index=1,
                conversion_type=ConversionType.COPIED,
            ),
        },
    )

    # Mock the media_info for the converted file to match its stream_sources
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        side_effect=[
            source_file.media_info,  # First call is for source_file
            MediaInfo(
                streams=(
                    Stream(codec_type="video", index=0),
                    Stream(codec_type="audio", index=1),
                )
            ),  # Second call is for converted_file
        ],
    )

    verify_streams(converted_file)
    assert mock_get_md5.call_count == 2


@pytest.mark.unit
def test_verify_streams_hash_mismatch(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that verify_streams fails when hashes of copied streams mismatch."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )
    source_file = video_file_factory(streams=[Stream(codec_type="audio", index=0)])
    converted_file = converted_video_file_factory(
        source_video_file=source_file,
        stream_sources={
            0: StreamSource(
                source_video_file=source_file,
                source_stream_index=0,
                conversion_type=ConversionType.COPIED,
            )
        },
    )
    mocker.patch(
        "ts2mp4.video_file.get_media_info",
        side_effect=[
            source_file.media_info,
            MediaInfo(streams=(Stream(codec_type="audio", index=0),)),
        ],
    )

    with pytest.raises(StreamIntegrityError, match="MD5 hash mismatch"):
        verify_streams(converted_file)
