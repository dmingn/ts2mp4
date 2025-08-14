"""Unit and integration tests for the audio_reencoder module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import (
    AudioReEncodedVideoFile,
    StreamSourcesForAudioReEncoding,
    _build_audio_convert_args,
    _build_ffmpeg_args_from_stream_sources,
    _build_stream_sources_for_audio_re_encoding,
    re_encode_mismatched_audio_streams,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.media_info import Stream, get_media_info
from ts2mp4.video_file import ConversionType, StreamSource, StreamSources, VideoFile


@pytest.mark.unit
def test_build_audio_convert_args(mocker: MockerFixture) -> None:
    """Test that audio convert arguments are built correctly."""
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=False)
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = Stream(
        index=1,
        codec_name="aac",
        codec_type="audio",
        sample_rate=48000,
        channels=2,
        profile="LC",
        bit_rate=192000,
    )
    args = _build_audio_convert_args(mock_stream_source, 1)
    assert args == [
        "-codec:1",
        "aac",
        "-ar:1",
        "48000",
        "-ac:1",
        "2",
        "-profile:1",
        "aac_low",
        "-b:1",
        "192000",
        "-bsf:1",
        "aac_adtstoasc",
    ]


@pytest.mark.unit
def test_build_audio_convert_args_with_libfdk_aac(mocker: MockerFixture) -> None:
    """Test that libfdk_aac is used when available for audio conversion."""
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=True)
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = Stream(
        index=1,
        codec_name="aac",
        codec_type="audio",
    )
    args = _build_audio_convert_args(mock_stream_source, 1)
    assert "libfdk_aac" in args


@pytest.mark.unit
def test_build_audio_convert_args_without_libfdk_aac(mocker: MockerFixture) -> None:
    """Test that a warning is logged when libfdk_aac is not available for audio conversion."""
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=False)
    mock_logger_warning = mocker.patch("ts2mp4.audio_reencoder.logger.warning")
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = Stream(
        index=1,
        codec_name="aac",
        codec_type="audio",
    )
    args = _build_audio_convert_args(mock_stream_source, 1)
    assert "aac" in args
    mock_logger_warning.assert_called_once_with(
        "libfdk_aac is not available. Falling back to the default AAC encoder."
    )


@pytest.mark.unit
def test_build_audio_convert_args_with_none_values(mocker: MockerFixture) -> None:
    """Test that audio convert arguments are built correctly with minimal stream info."""
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=False)
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = Stream(
        index=1, codec_name="aac", codec_type="audio"
    )
    args = _build_audio_convert_args(mock_stream_source, 1)
    assert args == ["-codec:1", "aac", "-bsf:1", "aac_adtstoasc"]


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
    result_video = re_encode_mismatched_audio_streams(
        original_file=VideoFile(path=ts_file),
        encoded_file=VideoFile(path=encoded_file_with_missing_stream),
        output_file=output_file,
    )

    # 3. Verify the output file
    assert result_video is not None
    assert isinstance(result_video, AudioReEncodedVideoFile)
    assert result_video.path == output_file

    output_media_info = result_video.media_info
    original_media_info = get_media_info(ts_file)

    assert len(output_media_info.streams) == len(original_media_info.streams)
    # Further checks could be added here, e.g., comparing stream MD5s


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams_no_re_encoding_needed(
    tmp_path: Path, ts_file: Path
) -> None:
    """Tests that the function returns None when no re-encoding is needed."""
    output_file = tmp_path / "output.mp4"

    # By using the same file for original and encoded, we ensure that stream
    # hashes match and no re-encoding should be triggered.
    result_video = re_encode_mismatched_audio_streams(
        original_file=VideoFile(path=ts_file),
        encoded_file=VideoFile(path=ts_file),
        output_file=output_file,
    )

    assert result_video is None
    assert not output_file.exists()


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_no_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that all streams are marked as COPIED when hashes match."""
    mock_original_video_file = mocker.MagicMock(spec=VideoFile)
    mock_original_video_file.path = Path("original.ts")
    mock_original_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h264"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
    ]

    mock_encoded_video_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_video_file.path = Path("encoded.mp4")
    mock_encoded_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h265"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
    ]

    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=True)

    stream_sources = _build_stream_sources_for_audio_re_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    assert len(stream_sources) == 2

    video_source = next(
        s for s in stream_sources if s.source_stream.codec_type == "video"
    )
    assert video_source.source_video_file == mock_encoded_video_file
    assert video_source.conversion_type == ConversionType.COPIED

    audio_source = next(
        s for s in stream_sources if s.source_stream.codec_type == "audio"
    )
    assert audio_source.source_video_file == mock_encoded_video_file
    assert audio_source.conversion_type == ConversionType.COPIED


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_with_mismatch(
    mocker: MockerFixture,
) -> None:
    """Tests that mismatched audio streams are marked as CONVERTED."""
    mock_original_video_file = mocker.MagicMock(spec=VideoFile)
    mock_original_video_file.path = Path("original.ts")
    mock_original_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h264"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
        Stream(codec_type="audio", index=2, codec_name="aac"),
    ]

    mock_encoded_video_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_video_file.path = Path("encoded.mp4")
    mock_encoded_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h265"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
        Stream(codec_type="audio", index=2, codec_name="aac"),
    ]

    mocker.patch(
        "ts2mp4.audio_reencoder.compare_stream_hashes", side_effect=[True, False]
    )

    stream_sources = _build_stream_sources_for_audio_re_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    assert len(stream_sources) == 3

    video_source = stream_sources[0]
    assert video_source.source_video_file == mock_encoded_video_file
    assert video_source.conversion_type == ConversionType.COPIED

    copied_audio_source = stream_sources[1]
    assert copied_audio_source.source_video_file == mock_encoded_video_file
    assert copied_audio_source.conversion_type == ConversionType.COPIED

    converted_audio_source = stream_sources[2]
    assert converted_audio_source.source_video_file == mock_original_video_file
    assert converted_audio_source.conversion_type == ConversionType.CONVERTED


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_missing_stream(
    mocker: MockerFixture,
) -> None:
    """Tests that missing audio streams in encoded file are marked as CONVERTED."""
    mock_original_video_file = mocker.MagicMock(spec=VideoFile)
    mock_original_video_file.path = Path("original.ts")
    mock_original_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h264"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
    ]

    mock_encoded_video_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_video_file.path = Path("encoded.mp4")
    mock_encoded_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h265")
    ]

    stream_sources = _build_stream_sources_for_audio_re_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    assert len(stream_sources) == 2

    converted_audio_source = stream_sources[1]
    assert converted_audio_source.source_video_file == mock_original_video_file
    assert converted_audio_source.conversion_type == ConversionType.CONVERTED


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_extra_stream_in_encoded(
    mocker: MockerFixture,
) -> None:
    """Tests that an error is raised if encoded file has more audio streams."""
    mock_original_video_file = mocker.MagicMock(spec=VideoFile)
    mock_original_video_file.path = Path("original.ts")
    mock_original_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h264"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
    ]

    mock_encoded_video_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_video_file.path = Path("encoded.mp4")
    mock_encoded_video_file.media_info.streams = [
        Stream(codec_type="video", index=0, codec_name="h265"),
        Stream(codec_type="audio", index=1, codec_name="aac"),
        Stream(codec_type="audio", index=2, codec_name="aac"),
    ]

    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=True)

    with pytest.raises(RuntimeError):
        _build_stream_sources_for_audio_re_encoding(
            mock_original_video_file, mock_encoded_video_file
        )


@pytest.mark.unit
def test_build_ffmpeg_args_from_stream_sources(mocker: MockerFixture) -> None:
    """Tests that FFmpeg arguments are correctly built from a StreamSources object."""
    mock_original_file = mocker.MagicMock(spec=VideoFile)
    mock_original_file.path = Path("original.ts")
    mock_encoded_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_file.path = Path("encoded.mp4")

    ss1 = mocker.MagicMock(spec=StreamSource)
    ss1.source_video_file = mock_encoded_file
    ss1.source_stream.index = 0
    ss1.conversion_type = ConversionType.COPIED
    ss1.source_stream.codec_type = "video"

    ss2 = mocker.MagicMock(spec=StreamSource)
    ss2.source_video_file = mock_encoded_file
    ss2.source_stream.index = 1
    ss2.conversion_type = ConversionType.COPIED
    ss2.source_stream.codec_type = "audio"

    ss3 = mocker.MagicMock(spec=StreamSource)
    ss3.source_video_file = mock_original_file
    ss3.source_stream.index = 2
    ss3.conversion_type = ConversionType.CONVERTED
    ss3.source_stream.codec_type = "audio"

    stream_sources = mocker.MagicMock(spec=StreamSourcesForAudioReEncoding)
    stream_sources.__iter__.return_value = [ss1, ss2, ss3]

    mock_build_audio_convert_args = mocker.patch(
        "ts2mp4.audio_reencoder._build_audio_convert_args",
        return_value=["-codec:2", "libfdk_aac"],
    )

    output_path = Path("output.mp4")
    args = _build_ffmpeg_args_from_stream_sources(stream_sources, output_path)

    expected_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        "encoded.mp4",
        "-i",
        "original.ts",
        "-map",
        "0:0",  # Map video from encoded_file (input 0)
        "-codec:0",
        "copy",
        "-map",
        "0:1",  # Map first audio from encoded_file (input 0)
        "-codec:1",
        "copy",
        "-map",
        "1:2",  # Map second audio from original_file (input 1)
        "-codec:2",  # Mocked return value
        "libfdk_aac",
        "-f",
        "mp4",
        "output.mp4",
    ]

    assert args == expected_args
    mock_build_audio_convert_args.assert_called_once_with(ss3, 2)


@pytest.mark.unit
def test_stream_sources_for_audio_re_encoding_validation_success(
    mocker: MockerFixture,
) -> None:
    """Tests that StreamSourcesForAudioReEncoding can be created with valid data."""
    mock_original_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_file = mocker.MagicMock(spec=VideoFile)

    valid_sources = StreamSources(
        [
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_encoded_file,
                conversion_type=ConversionType.COPIED,
                source_stream=mocker.MagicMock(spec=Stream, codec_type="video"),
            ),
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_original_file,
                conversion_type=ConversionType.CONVERTED,
                source_stream=mocker.MagicMock(spec=Stream, codec_type="audio"),
            ),
        ]
    )
    # This should not raise an error
    StreamSourcesForAudioReEncoding(valid_sources)


@pytest.mark.unit
@pytest.mark.parametrize(
    "modifier, error_message",
    [
        ("no_video", "At least one video stream is required."),
        ("video_not_copied", "All video streams must be copied."),
        (
            "video_from_original",
            "All copied streams must come from the same encoded file.",
        ),
        ("no_audio", "At least one audio stream is required."),
        (
            "copied_audio_from_original",
            "All copied streams must come from the same encoded file.",
        ),
        (
            "converted_audio_from_encoded",
            "Original and encoded files cannot be the same when re-encoding.",
        ),
        ("unsupported_stream", "Only video and audio streams are supported."),
        (
            "only_converted",
            "At least one video stream is required.",
        ),  # This now fails at the video check
        (
            "converted_from_multiple",
            "All converted streams must come from the same original file.",
        ),
    ],
)
def test_stream_sources_for_audio_re_encoding_validation_failures(
    modifier: str, error_message: str, mocker: MockerFixture
) -> None:
    """Tests the validation rules in StreamSourcesForAudioReEncoding.__new__."""
    mock_original_file = mocker.MagicMock(spec=VideoFile)
    mock_encoded_file = mocker.MagicMock(spec=VideoFile)

    # Create a base valid list of sources
    sources = [
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_encoded_file,
            conversion_type=ConversionType.COPIED,
            source_stream=mocker.MagicMock(spec=Stream, codec_type="video"),
        ),
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_encoded_file,
            conversion_type=ConversionType.COPIED,
            source_stream=mocker.MagicMock(spec=Stream, codec_type="audio"),
        ),
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_original_file,
            conversion_type=ConversionType.CONVERTED,
            source_stream=mocker.MagicMock(spec=Stream, codec_type="audio"),
        ),
    ]

    # Modify the sources based on the test case
    if modifier == "no_video":
        sources = [s for s in sources if s.source_stream.codec_type != "video"]
    elif modifier == "video_not_copied":
        sources[0].conversion_type = ConversionType.CONVERTED
    elif modifier == "video_from_original":
        sources[0].source_video_file = mock_original_file
    elif modifier == "no_audio":
        sources = [s for s in sources if s.source_stream.codec_type != "audio"]
    elif modifier == "copied_audio_from_original":
        sources.append(
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_original_file,  # Invalid
                conversion_type=ConversionType.COPIED,
                source_stream=mocker.MagicMock(spec=Stream, codec_type="audio"),
            )
        )
    elif modifier == "converted_audio_from_encoded":
        sources[2].source_video_file = mock_encoded_file  # Invalid
    elif modifier == "unsupported_stream":
        sources.append(
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_original_file,
                conversion_type=ConversionType.CONVERTED,
                source_stream=mocker.MagicMock(spec=Stream, codec_type="subtitle"),
            )
        )
    elif modifier == "only_converted":
        sources = [sources[2]]
    elif modifier == "converted_from_multiple":
        mock_another_original = mocker.MagicMock(spec=VideoFile)
        sources.append(
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_another_original,
                conversion_type=ConversionType.CONVERTED,
                source_stream=mocker.MagicMock(spec=Stream, codec_type="audio"),
            )
        )

    with pytest.raises(ValueError, match=error_message):
        StreamSourcesForAudioReEncoding(StreamSources(sources))
