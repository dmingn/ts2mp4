"""Unit tests for the stream_integrity module."""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.stream_integrity import StreamIntegrityError, verify_streams
from ts2mp4.video_file import (
    ConvertedVideoFile,
    VideoFile,
)


@pytest.mark.unit
def test_verify_streams_simple_success(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that verify_streams succeeds with identical simple video files."""
    mock_get_md5 = mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash"
    )
    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        return_value=MediaInfo(streams=(Stream(codec_type="audio", index=0),)),
    )

    file1 = video_file_factory()
    file2 = video_file_factory()

    verify_streams(file1, file2, "audio")
    assert mock_get_md5.call_count == 2


@pytest.mark.unit
def test_verify_streams_simple_hash_mismatch(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that verify_streams fails when hashes mismatch for simple files."""
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )
    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        return_value=MediaInfo(streams=(Stream(codec_type="audio", index=0),)),
    )

    file1 = video_file_factory()
    file2 = video_file_factory()

    with pytest.raises(StreamIntegrityError, match="MD5 hash mismatch"):
        verify_streams(file1, file2, "audio")


@pytest.mark.unit
def test_verify_streams_simple_stream_count_mismatch(
    video_file_factory: Callable[..., VideoFile], mocker: MockerFixture
) -> None:
    """Test that verify_streams fails with different stream counts."""
    file1 = video_file_factory()
    file2 = video_file_factory()

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=(Stream(codec_type="audio", index=0),)),
            MediaInfo(streams=()),
        ],
    )

    with pytest.raises(
        StreamIntegrityError, match="Mismatch in number of audio streams"
    ):
        verify_streams(file1, file2, "audio")


@pytest.mark.unit
def test_verify_streams_converted_file_success(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test verify_streams success with a converted file against its source."""
    source_file = video_file_factory()
    converted_file = converted_video_file_factory(source_video_file=source_file)

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=(Stream(codec_type="video", index=0),)),  # Converted file
            MediaInfo(streams=(Stream(codec_type="video", index=0),)),  # Source file
        ],
    )
    mock_get_md5 = mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash"
    )

    verify_streams(converted_file, source_file, "video")
    assert mock_get_md5.call_count == 2


@pytest.mark.unit
def test_verify_streams_converted_file_hash_mismatch(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test verify_streams failure with a converted file due to hash mismatch."""
    source_file = video_file_factory()
    converted_file = converted_video_file_factory(source_video_file=source_file)

    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        side_effect=[
            MediaInfo(streams=(Stream(codec_type="video", index=0),)),
            MediaInfo(streams=(Stream(codec_type="video", index=0),)),
        ],
    )
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )

    with pytest.raises(StreamIntegrityError, match="MD5 hash mismatch"):
        verify_streams(converted_file, source_file, "video")


@pytest.mark.unit
def test_verify_streams_converted_skips_unrelated_source(
    video_file_factory: Callable[..., VideoFile],
    converted_video_file_factory: Callable[..., ConvertedVideoFile],
    mocker: MockerFixture,
) -> None:
    """Test that verify_streams skips checks against an unrelated source file."""
    source_file1 = video_file_factory(filename="source1.ts")
    source_file2 = video_file_factory(filename="source2.ts")
    converted_file = converted_video_file_factory(source_video_file=source_file1)

    mock_logger_warning = mocker.patch("ts2mp4.stream_integrity.logger.warning")
    mock_get_md5 = mocker.patch("ts2mp4.stream_integrity.get_stream_md5")
    mocker.patch(
        "ts2mp4.stream_integrity.get_media_info",
        return_value=MediaInfo(streams=(Stream(codec_type="video", index=0),)),
    )

    # Compare converted file against an unrelated source
    verify_streams(converted_file, source_file2, "video")

    # Ensure no hashes were calculated and a warning was logged
    mock_get_md5.assert_not_called()
    mock_logger_warning.assert_called_once_with(
        "No matching video streams found for verification in "
        "converted.mp4 originating from source2.ts."
    )
