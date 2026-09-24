"""Unit and integration tests for the audio_encoder module."""

from pathlib import Path
from typing import Callable, Literal, cast

import pytest
from pytest_mock import MockerFixture

from tests.helpers import stream_at
from ts2mp4.audio_encoder import (
    StreamSourceForAudioEncoding,
    StreamSourcesForAudioEncoding,
    _build_audio_encode_args,
    _build_ffmpeg_args_from_stream_sources,
    _build_stream_sources_for_audio_encoding,
    encode_mismatched_audio_streams,
)
from ts2mp4.ffmpeg import execute_ffmpeg
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_source import StreamSource, StreamSources
from ts2mp4.video_encoder import (
    StreamSourcesForVideoEncoding,
    VideoEncodedFile,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


def _patch_audio_probe(
    mocker: MockerFixture,
    path: Path,
    *,
    index: int = 1,
    codec_name: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    profile: str | None = None,
    bit_rate: int | None = None,
) -> None:
    """Stub probe_file with a single audio stream at ``index``."""
    mocker.patch(
        "ts2mp4.video_file.probe_file",
        return_value=FFprobeOutput(
            streams=(
                FFprobeStream(
                    index=index,
                    codec_type="audio",
                    codec_name=codec_name,
                    sample_rate=sample_rate,
                    channels=channels,
                    profile=profile,
                    bit_rate=bit_rate,
                ),
            )
        ),
    )


@pytest.fixture
def mock_original_video_file(mocker: MockerFixture, tmp_path: Path) -> VideoFile:
    """Create a VideoFile for the original file with stubbed probe streams."""
    path = tmp_path / "original.ts"
    path.touch()
    video_file = VideoFile(path=path)

    mocker.patch(
        "ts2mp4.video_file.probe_file",
        return_value=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(
                    codec_type="audio", index=1, codec_name="aac", channels=2
                ),
                FFprobeStream(
                    codec_type="audio", index=2, codec_name="aac", channels=2
                ),
            )
        ),
    )
    return video_file


@pytest.fixture
def mock_video_encoded_file_factory(
    mocker: MockerFixture, tmp_path: Path
) -> Callable[..., VideoEncodedFile]:
    """Create a factory for mock VideoEncodedFile objects."""

    def _factory(
        original_file: VideoFile,
        encoded_streams_indices: list[int],
        file_name: str = "encoded.mp4",
    ) -> VideoEncodedFile:
        dummy_file = tmp_path / file_name
        dummy_file.touch()
        encoded_vf = VideoFile(path=dummy_file)

        mock_encoded_file = mocker.MagicMock(spec=VideoEncodedFile)
        mock_encoded_file.path = dummy_file

        original_streams = original_file.streams

        encoded_streams = frozenset(
            (
                VideoStream(file=encoded_vf, index=new_index)
                if isinstance(stream_at(original_streams, i), VideoStream)
                else AudioStream(file=encoded_vf, index=new_index)
            )
            for new_index, i in enumerate(encoded_streams_indices)
        )
        type(mock_encoded_file).streams = mocker.PropertyMock(
            return_value=encoded_streams
        )

        stream_sources = StreamSources(
            root=tuple(
                StreamSource(
                    source_stream=stream_at(original_streams, i),
                    conversion_type=(
                        "encoded"
                        if isinstance(stream_at(original_streams, i), VideoStream)
                        else "copied"
                    ),
                )
                for i in encoded_streams_indices
            )
        )
        type(mock_encoded_file).stream_sources = mocker.PropertyMock(
            return_value=stream_sources
        )

        return cast(VideoEncodedFile, mock_encoded_file)

    return _factory


@pytest.mark.unit
def test_build_stream_sources_for_audio_encoding_no_mismatch(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Tests that all streams are marked as COPIED when hashes match."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1, 2]
    )
    mocker.patch("ts2mp4.audio_encoder.compare_stream_hashes", return_value=True)

    # Act
    stream_sources = _build_stream_sources_for_audio_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    # Assert
    assert len(stream_sources) == 3
    assert all(s.conversion_type == "copied" for s in stream_sources)
    assert all(
        s.source_stream.file.path == mock_encoded_video_file.path
        for s in stream_sources
    )


@pytest.mark.unit
def test_build_stream_sources_for_audio_encoding_with_mismatch(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Tests that mismatched audio streams are marked as CONVERTED."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1, 2]
    )
    mocker.patch(
        "ts2mp4.audio_encoder.compare_stream_hashes", side_effect=[True, False]
    )

    # Act
    stream_sources = _build_stream_sources_for_audio_encoding(
        mock_original_video_file, mock_encoded_video_file
    )

    # Assert
    source_map = {s.source_stream.index: s for s in stream_sources}
    assert source_map[0].conversion_type == "copied"
    assert source_map[1].conversion_type == "copied"
    assert source_map[2].conversion_type == "encoded"
    assert source_map[2].source_stream.file.path == mock_original_video_file.path


@pytest.mark.unit
def test_build_stream_sources_for_audio_encoding_missing_stream_raises_error(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Tests that a missing stream raises a RuntimeError."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1]
    )
    mocker.patch("ts2mp4.audio_encoder.compare_stream_hashes", return_value=True)

    # Act & Assert
    with pytest.raises(RuntimeError, match="is missing a required stream"):
        _build_stream_sources_for_audio_encoding(
            mock_original_video_file, mock_encoded_video_file
        )


@pytest.mark.unit
def test_build_audio_encode_args(mocker: MockerFixture, tmp_path: Path) -> None:
    """Test that audio convert arguments are built correctly."""
    # Arrange
    mocker.patch("ts2mp4.audio_encoder.is_libfdk_aac_available", return_value=False)
    path = tmp_path / "audio.ts"
    path.touch()
    _patch_audio_probe(
        mocker,
        path,
        codec_name="aac",
        sample_rate=48000,
        channels=2,
        profile="LC",
        bit_rate=192000,
    )
    video_file = VideoFile(path=path)
    stream_source: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=video_file, index=1),
        conversion_type="encoded",
    )

    # Act
    args = _build_audio_encode_args(stream_source, 1)

    # Assert
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
def test_build_audio_encode_args_with_libfdk_aac(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that libfdk_aac is used when available for audio conversion."""
    # Arrange
    mocker.patch("ts2mp4.audio_encoder.is_libfdk_aac_available", return_value=True)
    path = tmp_path / "audio.ts"
    path.touch()
    _patch_audio_probe(mocker, path, codec_name="aac")
    video_file = VideoFile(path=path)
    stream_source: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=video_file, index=1),
        conversion_type="encoded",
    )

    # Act
    args = _build_audio_encode_args(stream_source, 1)

    # Assert
    assert "libfdk_aac" in args


@pytest.mark.unit
def test_build_audio_encode_args_without_libfdk_aac(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that a warning is logged when libfdk_aac is not available for audio conversion."""
    # Arrange
    mocker.patch("ts2mp4.audio_encoder.is_libfdk_aac_available", return_value=False)
    mock_logger_warning = mocker.patch("ts2mp4.audio_encoder.logger.warning")
    path = tmp_path / "audio.ts"
    path.touch()
    _patch_audio_probe(mocker, path, codec_name="aac")
    video_file = VideoFile(path=path)
    stream_source: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=video_file, index=1),
        conversion_type="encoded",
    )

    # Act
    args = _build_audio_encode_args(stream_source, 1)

    # Assert
    assert "aac" in args
    mock_logger_warning.assert_called_once_with(
        "libfdk_aac is not available. Falling back to the default AAC encoder."
    )


@pytest.mark.unit
def test_build_audio_encode_args_with_none_values(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Test that audio convert arguments are built correctly with minimal stream info."""
    # Arrange
    mocker.patch("ts2mp4.audio_encoder.is_libfdk_aac_available", return_value=False)
    path = tmp_path / "audio.ts"
    path.touch()
    _patch_audio_probe(mocker, path, codec_name="aac")
    video_file = VideoFile(path=path)
    stream_source: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=video_file, index=1),
        conversion_type="encoded",
    )

    # Act
    args = _build_audio_encode_args(stream_source, 1)

    # Assert
    assert args == ["-codec:1", "aac", "-bsf:1", "aac_adtstoasc"]


@pytest.mark.unit
def test_build_audio_encode_args_raises_for_unsupported_codec(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Test that an error is raised for unsupported audio codecs."""
    # Arrange
    path = tmp_path / "audio.ts"
    path.touch()
    _patch_audio_probe(mocker, path, codec_name="mp3")
    video_file = VideoFile(path=path)
    stream_source: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=video_file, index=1),
        conversion_type="encoded",
    )

    # Act & Assert
    with pytest.raises(
        NotImplementedError,
        match="Encoding is currently only supported for aac audio codec.",
    ):
        _build_audio_encode_args(stream_source, 1)


@pytest.mark.integration
def test_encode_mismatched_audio_streams_integration(
    tmp_path: Path, ts_file: Path
) -> None:
    """Test the audio encoding function with a real video file."""
    # Arrange
    original_video_file = VideoFile(path=ts_file)
    original_streams = original_video_file.streams

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

    encoded_video_file = VideoEncodedFile(
        path=encoded_file_path,
        stream_sources=StreamSourcesForVideoEncoding(
            root=(
                StreamSource(
                    source_stream=stream_at(original_streams, 0),
                    conversion_type="encoded",
                ),
                StreamSource(
                    source_stream=stream_at(original_streams, 1),
                    conversion_type="copied",
                ),
            )
        ),
    )

    output_file = tmp_path / "output.mp4"

    # Act & Assert
    with pytest.raises(RuntimeError, match="is missing a required stream"):
        encode_mismatched_audio_streams(
            original_file=original_video_file,
            encoded_file=encoded_video_file,
            output_file=output_file,
        )


@pytest.mark.integration
def test_encode_mismatched_audio_streams_no_encoding_needed(
    tmp_path: Path, ts_file: Path
) -> None:
    """Test that the function returns None when no encoding is needed."""
    # Arrange
    original_video_file = VideoFile(path=ts_file)
    original_streams = original_video_file.streams

    encoded_stream_sources = StreamSourcesForVideoEncoding(
        root=tuple(
            StreamSource(
                source_stream=s,
                conversion_type=("encoded" if isinstance(s, VideoStream) else "copied"),
            )
            for s in sorted(original_streams)
            if isinstance(s, (VideoStream, AudioStream))
        )
    )
    encoded_video_file = VideoEncodedFile(
        path=ts_file, stream_sources=encoded_stream_sources
    )

    output_file = tmp_path / "output.mp4"

    # Act
    result_video = encode_mismatched_audio_streams(
        original_file=original_video_file,
        encoded_file=encoded_video_file,
        output_file=output_file,
    )

    # Assert
    assert result_video is None
    assert not output_file.exists()


@pytest.mark.unit
def test_build_ffmpeg_args_from_stream_sources(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Tests that FFmpeg arguments are correctly built from a StreamSources object."""
    # Arrange
    dummy_original_file = tmp_path / "original.ts"
    dummy_original_file.touch()
    original_file = VideoFile(path=dummy_original_file)

    dummy_encoded_file = tmp_path / "encoded.mp4"
    dummy_encoded_file.touch()
    encoded_file = VideoFile(path=dummy_encoded_file)

    ss1: StreamSource[VideoStream, Literal["copied"]] = StreamSource(
        source_stream=VideoStream(file=encoded_file, index=0),
        conversion_type="copied",
    )
    ss2: StreamSource[AudioStream, Literal["copied"]] = StreamSource(
        source_stream=AudioStream(file=encoded_file, index=1),
        conversion_type="copied",
    )
    ss3: StreamSource[AudioStream, Literal["encoded"]] = StreamSource(
        source_stream=AudioStream(file=original_file, index=2),
        conversion_type="encoded",
    )

    stream_sources = StreamSourcesForAudioEncoding(root=(ss1, ss2, ss3))

    mock_build_audio_encode_args = mocker.patch(
        "ts2mp4.audio_encoder._build_audio_encode_args",
        return_value=["-codec:2", "libfdk_aac"],
    )
    mocker.patch(
        "ts2mp4.audio_encoder.build_disposition_args",
        return_value=[
            "-disposition:0",
            "default",
            "-disposition:1",
            "default",
            "-disposition:2",
            "0",
        ],
    )

    output_path = Path("output.mp4")
    expected_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(encoded_file.path),
        "-i",
        str(original_file.path),
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
        "-disposition:0",
        "default",
        "-disposition:1",
        "default",
        "-disposition:2",
        "0",
        "-f",
        "mp4",
        str(output_path),
    ]

    # Act
    args = _build_ffmpeg_args_from_stream_sources(stream_sources, output_path)

    # Assert
    assert args == expected_args
    mock_build_audio_encode_args.assert_called_once_with(ss3, 2)


@pytest.mark.unit
def test_stream_sources_for_audio_encoding_validation_success(
    tmp_path: Path,
) -> None:
    """StreamSourcesForAudioEncoding accepts a valid copied+encoded mix."""
    # Arrange
    dummy_original_file = tmp_path / "original.ts"
    dummy_original_file.touch()
    original_file = VideoFile(path=dummy_original_file)

    dummy_encoded_file = tmp_path / "encoded.mp4"
    dummy_encoded_file.touch()
    encoded_file = VideoFile(path=dummy_encoded_file)

    valid_sources: list[StreamSourceForAudioEncoding] = [
        StreamSource(
            conversion_type="copied",
            source_stream=VideoStream(file=encoded_file, index=0),
        ),
        StreamSource(
            conversion_type="encoded",
            source_stream=AudioStream(file=original_file, index=1),
        ),
    ]

    # Act & Assert
    StreamSourcesForAudioEncoding(root=tuple(valid_sources))


@pytest.mark.unit
@pytest.mark.parametrize(
    "modifier, error_message",
    [
        ("no_video", "At least one video stream is required."),
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
            "encoded_audio_from_encoded",
            "Original and encoded files cannot be the same when encoding audio.",
        ),
        ("only_encoded", "At least one video stream is required."),
        (
            "encoded_from_multiple",
            "All streams to encode must come from the same original file.",
        ),
    ],
)
def test_stream_sources_for_audio_encoding_value_validation_failures(
    modifier: str, error_message: str, tmp_path: Path
) -> None:
    """Tests the validation rules in StreamSourcesForAudioEncoding."""
    # Arrange
    dummy_original_file = tmp_path / "original.ts"
    dummy_original_file.touch()
    original_file = VideoFile(path=dummy_original_file)

    dummy_encoded_file = tmp_path / "encoded.mp4"
    dummy_encoded_file.touch()
    encoded_file = VideoFile(path=dummy_encoded_file)

    dummy_another_original = tmp_path / "another.ts"
    dummy_another_original.touch()
    another_original = VideoFile(path=dummy_another_original)

    sources: list[StreamSourceForAudioEncoding] = [
        StreamSource(
            conversion_type="copied",
            source_stream=VideoStream(file=encoded_file, index=0),
        ),
        StreamSource(
            conversion_type="copied",
            source_stream=AudioStream(file=encoded_file, index=1),
        ),
        StreamSource(
            conversion_type="encoded",
            source_stream=AudioStream(file=original_file, index=2),
        ),
    ]

    if modifier == "no_video":
        sources = [s for s in sources if not isinstance(s.source_stream, VideoStream)]
    elif modifier == "video_from_original":
        sources[0] = StreamSource(
            source_stream=VideoStream(
                file=original_file, index=sources[0].source_stream.index
            ),
            conversion_type=sources[0].conversion_type,
        )
    elif modifier == "no_audio":
        sources = [s for s in sources if not isinstance(s.source_stream, AudioStream)]
    elif modifier == "copied_audio_from_original":
        sources.append(
            StreamSource(
                conversion_type="copied",
                source_stream=AudioStream(file=original_file, index=3),
            )
        )
    elif modifier == "encoded_audio_from_encoded":
        sources[2] = StreamSource(
            source_stream=AudioStream(
                file=encoded_file, index=sources[2].source_stream.index
            ),
            conversion_type=sources[2].conversion_type,
        )
    elif modifier == "only_encoded":
        sources = [sources[2]]
    elif modifier == "encoded_from_multiple":
        sources.append(
            StreamSource(
                conversion_type="encoded",
                source_stream=AudioStream(file=another_original, index=3),
            )
        )

    # Act & Assert
    with pytest.raises(ValueError, match=error_message):
        StreamSourcesForAudioEncoding(root=tuple(sources))


@pytest.mark.unit
@pytest.mark.parametrize(
    "stream_index_to_mismatch, mismatched_kind, expected_error_message_part",
    [
        (0, "audio", "expected to be 'video'"),
        (1, "video", "expected to be 'audio'"),
    ],
)
def test_build_stream_sources_for_audio_encoding_stream_type_mismatch_raises_error(
    mocker: MockerFixture,
    mock_original_video_file: VideoFile,
    stream_index_to_mismatch: int,
    mismatched_kind: Literal["audio", "video"],
    expected_error_message_part: str,
    tmp_path: Path,
) -> None:
    """Tests that a stream type mismatch raises a RuntimeError."""
    # Arrange
    encoded_file_path = tmp_path / "encoded.mp4"
    encoded_file_path.touch()
    encoded_vf = VideoFile(path=encoded_file_path)

    mock_encoded_video_file = mocker.MagicMock(spec=VideoEncodedFile)
    mock_encoded_video_file.path = encoded_file_path

    if mismatched_kind == "audio":
        mismatched_stream: VideoStream | AudioStream = AudioStream(
            file=encoded_vf, index=stream_index_to_mismatch
        )
    else:
        mismatched_stream = VideoStream(file=encoded_vf, index=stream_index_to_mismatch)

    initial_streams: frozenset[VideoStream | AudioStream] = frozenset(
        (
            VideoStream(file=encoded_vf, index=0),
            AudioStream(file=encoded_vf, index=1),
            AudioStream(file=encoded_vf, index=2),
        )
    )

    mismatched_streams = frozenset(
        mismatched_stream if s.index == stream_index_to_mismatch else s
        for s in initial_streams
    )

    type(mock_encoded_video_file).streams = mocker.PropertyMock(
        return_value=mismatched_streams
    )

    original_streams = mock_original_video_file.streams
    type(mock_encoded_video_file).stream_sources = mocker.PropertyMock(
        return_value=StreamSources(
            root=tuple(
                StreamSource(
                    source_stream=stream_at(original_streams, i),
                    conversion_type="copied",
                )
                for i in range(len(initial_streams))
            )
        )
    )

    mocker.patch("ts2mp4.audio_encoder.compare_stream_hashes", return_value=True)

    # Act & Assert
    with pytest.raises(RuntimeError) as excinfo:
        _build_stream_sources_for_audio_encoding(
            mock_original_video_file, mock_encoded_video_file
        )

    assert "Mismatch in stream types" in str(excinfo.value)
    assert expected_error_message_part in str(excinfo.value)
