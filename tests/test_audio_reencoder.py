"""Unit and integration tests for the audio_reencoder module."""

from pathlib import Path
from typing import Callable, cast

import pytest
from pytest_mock import MockerFixture

from ts2mp4.audio_reencoder import (
    StreamSourcesForAudioReEncoding,
    _build_audio_convert_args,
    _build_ffmpeg_args_from_stream_sources,
    _build_stream_sources_for_audio_re_encoding,
    re_encode_mismatched_audio_streams,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.initial_converter import (
    InitiallyConvertedVideoFile,
    StreamSourcesForInitialConversion,
)
from ts2mp4.media_info import AudioStream, OtherStream, VideoStream
from ts2mp4.video_file import ConversionType, StreamSource, StreamSources, VideoFile


@pytest.fixture
def mock_original_video_file(mocker: MockerFixture, tmp_path: Path) -> VideoFile:
    """Create a mock VideoFile object for the original file."""
    mock_file = mocker.MagicMock(spec=VideoFile)
    path = tmp_path / "original.ts"
    path.touch()
    mock_file.path = path

    original_video_stream = VideoStream(codec_type="video", index=0)
    original_audio_stream_1 = AudioStream(codec_type="audio", index=1, codec_name="aac")
    original_audio_stream_2 = AudioStream(codec_type="audio", index=2, codec_name="aac")

    all_streams = (
        original_video_stream,
        original_audio_stream_1,
        original_audio_stream_2,
    )

    mock_file.valid_streams = all_streams
    type(mock_file).media_info = mocker.PropertyMock(
        return_value=mocker.MagicMock(streams=all_streams)
    )
    return cast(VideoFile, mock_file)


@pytest.fixture
def mock_initially_converted_video_file_factory(
    mocker: MockerFixture,
) -> Callable[..., InitiallyConvertedVideoFile]:
    """Create a factory for mock InitiallyConvertedVideoFile objects."""

    def _factory(
        original_file: VideoFile,
        encoded_streams_indices: list[int],
        file_name: str = "encoded.mp4",
    ) -> InitiallyConvertedVideoFile:
        mock_encoded_file = mocker.MagicMock(spec=InitiallyConvertedVideoFile)
        mock_encoded_file.path = Path(file_name)

        original_streams = original_file.media_info.streams

        encoded_streams = tuple(
            (
                VideoStream(
                    codec_type="video",
                    index=new_index,
                )
                if original_streams[i].codec_type == "video"
                else AudioStream(
                    codec_type="audio",
                    index=new_index,
                    codec_name="aac",
                )
            )
            for new_index, i in enumerate(encoded_streams_indices)
        )
        type(mock_encoded_file).media_info = mocker.PropertyMock(
            return_value=mocker.MagicMock(streams=encoded_streams)
        )

        stream_sources = StreamSources(
            root=tuple(
                StreamSource(
                    source_video_file=original_file,
                    source_stream_index=i,
                    conversion_type=(
                        ConversionType.CONVERTED
                        if original_streams[i].codec_type == "video"
                        else ConversionType.COPIED
                    ),
                )
                for i in encoded_streams_indices
            )
        )
        type(mock_encoded_file).stream_sources = mocker.PropertyMock(
            return_value=stream_sources
        )

        return cast(InitiallyConvertedVideoFile, mock_encoded_file)

    return _factory


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_no_mismatch(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_initially_converted_video_file_factory: Callable[
        ..., InitiallyConvertedVideoFile
    ],
) -> None:
    """Tests that all streams are marked as COPIED when hashes match."""
    mock_encoded_video_file = mock_initially_converted_video_file_factory(
        mock_original_video_file, [0, 1, 2]
    )
    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=True)

    stream_sources = _build_stream_sources_for_audio_re_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    assert len(stream_sources) == 3
    assert all(s.conversion_type == ConversionType.COPIED for s in stream_sources)
    assert all(s.source_video_file == mock_encoded_video_file for s in stream_sources)


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_with_mismatch(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_initially_converted_video_file_factory: Callable[
        ..., InitiallyConvertedVideoFile
    ],
) -> None:
    """Tests that mismatched audio streams are marked as CONVERTED."""
    mock_encoded_video_file = mock_initially_converted_video_file_factory(
        mock_original_video_file, [0, 1, 2]
    )
    mocker.patch(
        "ts2mp4.audio_reencoder.compare_stream_hashes", side_effect=[True, False]
    )

    stream_sources = _build_stream_sources_for_audio_re_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    source_map = {s.source_stream.index: s for s in stream_sources}
    assert source_map[0].conversion_type == ConversionType.COPIED
    assert source_map[1].conversion_type == ConversionType.COPIED
    assert source_map[2].conversion_type == ConversionType.CONVERTED
    assert source_map[2].source_video_file == mock_original_video_file


@pytest.mark.unit
def test_build_stream_sources_for_audio_re_encoding_missing_stream_raises_error(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_initially_converted_video_file_factory: Callable[
        ..., InitiallyConvertedVideoFile
    ],
) -> None:
    """Tests that a missing stream raises a RuntimeError."""
    mock_encoded_video_file = mock_initially_converted_video_file_factory(
        mock_original_video_file, [0, 1]
    )
    mocker.patch("ts2mp4.audio_reencoder.compare_stream_hashes", return_value=True)

    with pytest.raises(RuntimeError, match="is missing a required stream"):
        _build_stream_sources_for_audio_re_encoding(
            mock_original_video_file, mock_encoded_video_file
        )


@pytest.mark.unit
def test_build_audio_convert_args(mocker: MockerFixture) -> None:
    """Test that audio convert arguments are built correctly."""
    mocker.patch("ts2mp4.audio_reencoder.is_libfdk_aac_available", return_value=False)
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = AudioStream(
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
    mock_stream_source.source_stream = AudioStream(
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
    mock_stream_source.source_stream = AudioStream(
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
    mock_stream_source.source_stream = AudioStream(
        index=1, codec_name="aac", codec_type="audio"
    )
    args = _build_audio_convert_args(mock_stream_source, 1)
    assert args == ["-codec:1", "aac", "-bsf:1", "aac_adtstoasc"]


@pytest.mark.unit
def test_build_audio_convert_args_raises_for_unsupported_codec(
    mocker: MockerFixture,
) -> None:
    """Test that an error is raised for unsupported audio codecs."""
    mock_stream_source = mocker.MagicMock(spec=StreamSource)
    mock_stream_source.source_stream = AudioStream(
        index=1,
        codec_name="mp3",  # Unsupported codec
        codec_type="audio",
    )
    with pytest.raises(
        NotImplementedError,
        match="Re-encoding is currently only supported for aac audio codec.",
    ):
        _build_audio_convert_args(mock_stream_source, 1)


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams_integration(
    tmp_path: Path, ts_file: Path
) -> None:
    """Test the re-encoding function with a real video file."""
    original_video_file = VideoFile(path=ts_file)
    original_streams = original_video_file.media_info.streams

    encoded_file_path = tmp_path / "encoded_missing_stream.mp4"
    execute_ffmpeg(
        [
            "-i",
            str(ts_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-codec",
            "copy",
            str(encoded_file_path),
        ]
    )

    encoded_video_file = InitiallyConvertedVideoFile(
        path=encoded_file_path,
        stream_sources=StreamSourcesForInitialConversion(
            root=(
                StreamSource(
                    source_video_file=original_video_file,
                    source_stream_index=original_streams[0].index,
                    conversion_type=ConversionType.CONVERTED,
                ),
                StreamSource(
                    source_video_file=original_video_file,
                    source_stream_index=original_streams[1].index,
                    conversion_type=ConversionType.COPIED,
                ),
            )
        ),
    )

    output_file = tmp_path / "output.mp4"
    with pytest.raises(RuntimeError, match="is missing a required stream"):
        re_encode_mismatched_audio_streams(
            original_file=original_video_file,
            encoded_file=encoded_video_file,
            output_file=output_file,
        )


@pytest.mark.integration
def test_re_encode_mismatched_audio_streams_no_re_encoding_needed(
    tmp_path: Path, ts_file: Path
) -> None:
    """Test that the function returns None when no re-encoding is needed."""
    original_video_file = VideoFile(path=ts_file)
    original_streams = original_video_file.media_info.streams

    encoded_stream_sources = StreamSourcesForInitialConversion(
        root=tuple(
            StreamSource(
                source_video_file=original_video_file,
                source_stream_index=s.index,
                conversion_type=(
                    ConversionType.CONVERTED
                    if s.codec_type == "video"
                    else ConversionType.COPIED
                ),
            )
            for s in original_streams
        )
    )
    encoded_video_file = InitiallyConvertedVideoFile(
        path=ts_file, stream_sources=encoded_stream_sources
    )

    output_file = tmp_path / "output.mp4"
    result_video = re_encode_mismatched_audio_streams(
        original_file=original_video_file,
        encoded_file=encoded_video_file,
        output_file=output_file,
    )

    assert result_video is None
    assert not output_file.exists()


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
        str(mock_encoded_file.path),
        "-i",
        str(mock_original_file.path),
        "-map",
        "0:0",
        "-codec:0",
        "copy",
        "-map",
        "0:1",
        "-codec:1",
        "copy",
        "-map",
        "1:2",
        "-codec:2",
        "libfdk_aac",
        "-f",
        "mp4",
        str(output_path),
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
    mock_original_file.path = Path("original.ts")
    mock_encoded_file.path = Path("encoded.mp4")

    valid_sources = [
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_encoded_file,
            conversion_type=ConversionType.COPIED,
            source_stream=mocker.MagicMock(spec=VideoStream, codec_type="video"),
        ),
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_original_file,
            conversion_type=ConversionType.CONVERTED,
            source_stream=mocker.MagicMock(spec=AudioStream, codec_type="audio"),
        ),
    ]
    StreamSourcesForAudioReEncoding(root=tuple(valid_sources))


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
        ),
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
    mock_original_file.path = Path("original.ts")
    mock_encoded_file.path = Path("encoded.mp4")
    mock_another_original = mocker.MagicMock(spec=VideoFile)
    mock_another_original.path = Path("another.ts")

    sources = [
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_encoded_file,
            conversion_type=ConversionType.COPIED,
            source_stream=mocker.MagicMock(spec=VideoStream, codec_type="video"),
        ),
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_encoded_file,
            conversion_type=ConversionType.COPIED,
            source_stream=mocker.MagicMock(spec=AudioStream, codec_type="audio"),
        ),
        mocker.MagicMock(
            spec=StreamSource,
            source_video_file=mock_original_file,
            conversion_type=ConversionType.CONVERTED,
            source_stream=mocker.MagicMock(spec=AudioStream, codec_type="audio"),
        ),
    ]

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
                source_video_file=mock_original_file,
                conversion_type=ConversionType.COPIED,
                source_stream=mocker.MagicMock(spec=AudioStream, codec_type="audio"),
            )
        )
    elif modifier == "converted_audio_from_encoded":
        sources[2].source_video_file = mock_encoded_file
    elif modifier == "unsupported_stream":
        sources.append(
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_original_file,
                conversion_type=ConversionType.CONVERTED,
                source_stream=mocker.MagicMock(spec=OtherStream, codec_type="subtitle"),
            )
        )
    elif modifier == "only_converted":
        sources = [sources[2]]
    elif modifier == "converted_from_multiple":
        sources.append(
            mocker.MagicMock(
                spec=StreamSource,
                source_video_file=mock_another_original,
                conversion_type=ConversionType.CONVERTED,
                source_stream=mocker.MagicMock(spec=AudioStream, codec_type="audio"),
            )
        )

    with pytest.raises(ValueError, match=error_message):
        StreamSourcesForAudioReEncoding(root=tuple(sources))
