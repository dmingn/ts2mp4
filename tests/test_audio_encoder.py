"""Unit and integration tests for the audio_encoder module."""

from pathlib import Path
from typing import Callable, Literal, cast

import pytest
from pytest_mock import MockerFixture

from tests.helpers import StubVideoFile, stream_at
from ts2mp4.audio_encoder import (
    FileConversionPlanForAudioEncoding,
    StreamConversionPlanForAudioEncoding,
    _build_encode_audio_for,
    build_file_conversion_plan_for_audio_encoding,
)
from ts2mp4.conversion_plan import (
    Copy,
    EncodeAudio,
    EncodeVideo,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import StreamWithConversionPlan
from ts2mp4.ffmpeg import SubprocessFFmpegRunner
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_integrity import IntegrityReport
from ts2mp4.video_encoder import (
    FileConversionPlanForVideoEncoding,
    VideoEncodedFile,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream

_NO_MISMATCH_REPORT = IntegrityReport(mismatched_output_indices=frozenset())


def _probed_audio_stream(
    tmp_path: Path,
    *,
    codec_name: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    profile: str | None = None,
    bit_rate: int | None = None,
) -> AudioStream:
    """Return the audio stream at index 1 of a file probed with the given fields."""
    path = tmp_path / "audio.ts"
    path.touch()
    video_file = StubVideoFile(
        path=path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(
                    index=1,
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
    return AudioStream(file=video_file, index=1)


@pytest.fixture
def mock_original_video_file(tmp_path: Path) -> VideoFile:
    """Create a VideoFile for the original file with stubbed probe streams."""
    path = tmp_path / "original.ts"
    path.touch()

    return StubVideoFile(
        path=path,
        stub_probe=FFprobeOutput(
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

        streams_with_conversion_plans: tuple[
            StreamWithConversionPlan[VideoStream | AudioStream], ...
        ] = tuple(
            StreamWithConversionPlan(
                stream=(
                    VideoStream(file=encoded_vf, index=new_index)
                    if isinstance(stream_at(original_streams, i), VideoStream)
                    else AudioStream(file=encoded_vf, index=new_index)
                ),
                conversion_plan=StreamConversionPlan(
                    source_stream=stream_at(original_streams, i),
                    conversion_method=(
                        EncodeVideo(codec="libx265", crf=23, preset="medium")
                        if isinstance(stream_at(original_streams, i), VideoStream)
                        else Copy()
                    ),
                ),
            )
            for new_index, i in enumerate(encoded_streams_indices)
        )
        type(mock_encoded_file).streams_with_conversion_plans = mocker.PropertyMock(
            return_value=streams_with_conversion_plans
        )

        return cast(VideoEncodedFile, mock_encoded_file)

    return _factory


@pytest.mark.unit
def test_build_file_conversion_plan_for_audio_encoding_raises_without_mismatch(
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """build_file_conversion_plan_for_audio_encoding rejects a report without mismatches."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1, 2]
    )

    # Act & Assert
    with pytest.raises(ValueError, match="must report at least one mismatch"):
        build_file_conversion_plan_for_audio_encoding(
            mock_original_video_file,
            mock_encoded_video_file,
            _NO_MISMATCH_REPORT,
            libfdk_aac_available=False,
        )


@pytest.mark.unit
def test_build_file_conversion_plan_for_audio_encoding_copies_matching_streams(
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Streams not reported as mismatched are copied from the encoded file."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1, 2]
    )
    integrity_report = IntegrityReport(mismatched_output_indices=frozenset({2}))

    # Act
    file_conversion_plan = build_file_conversion_plan_for_audio_encoding(
        mock_original_video_file,
        mock_encoded_video_file,
        integrity_report,
        libfdk_aac_available=False,
    )

    # Assert
    copied_source_indices = [
        s.source_stream.index
        for s in file_conversion_plan
        if isinstance(s.conversion_method, Copy)
    ]
    assert copied_source_indices == [0, 1]
    assert all(
        s.source_stream.file.path == mock_encoded_video_file.path
        for s in file_conversion_plan
        if isinstance(s.conversion_method, Copy)
    )


@pytest.mark.unit
def test_build_file_conversion_plan_for_audio_encoding_with_mismatch(
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Tests that the plan for a mismatched output stream encodes from the original."""
    # Arrange
    # Output stream 1 comes from original stream 2, and output 2 from original 1.
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 2, 1]
    )
    integrity_report = IntegrityReport(mismatched_output_indices=frozenset({2}))

    # Act
    file_conversion_plan = build_file_conversion_plan_for_audio_encoding(
        mock_original_video_file,
        mock_encoded_video_file,
        integrity_report,
        libfdk_aac_available=False,
    )

    # Assert
    encoded_source_streams = [
        s.source_stream
        for s in file_conversion_plan
        if isinstance(s.conversion_method, EncodeAudio)
    ]
    assert encoded_source_streams == [stream_at(mock_original_video_file.streams, 1)]


@pytest.mark.unit
def test_build_file_conversion_plan_for_audio_encoding_missing_stream_raises_error(
    mock_original_video_file: VideoFile,
    mock_video_encoded_file_factory: Callable[..., VideoEncodedFile],
) -> None:
    """Tests that a missing stream raises a RuntimeError."""
    # Arrange
    mock_encoded_video_file = mock_video_encoded_file_factory(
        mock_original_video_file, [0, 1]
    )
    integrity_report = IntegrityReport(mismatched_output_indices=frozenset({1}))

    # Act & Assert
    with pytest.raises(RuntimeError, match="is missing a required stream"):
        build_file_conversion_plan_for_audio_encoding(
            mock_original_video_file,
            mock_encoded_video_file,
            integrity_report,
            libfdk_aac_available=False,
        )


@pytest.mark.unit
def test_build_encode_audio_for_takes_settings_from_stream(tmp_path: Path) -> None:
    """_build_encode_audio_for takes sample rate, channels and bit rate from the stream."""
    # Arrange
    stream = _probed_audio_stream(
        tmp_path,
        codec_name="aac",
        sample_rate=48000,
        channels=2,
        bit_rate=192000,
    )

    # Act
    conversion_method = _build_encode_audio_for(stream, libfdk_aac_available=False)

    # Assert
    assert conversion_method == EncodeAudio(
        codec="aac",
        sample_rate=48000,
        channels=2,
        bit_rate=192000,
    )


@pytest.mark.unit
def test_build_encode_audio_for_maps_lc_profile_to_aac_low(tmp_path: Path) -> None:
    """_build_encode_audio_for maps the probed LC profile to FFmpeg's aac_low."""
    # Arrange
    stream = _probed_audio_stream(tmp_path, codec_name="aac", profile="LC")

    # Act
    conversion_method = _build_encode_audio_for(stream, libfdk_aac_available=False)

    # Assert
    assert conversion_method.profile == "aac_low"


@pytest.mark.unit
def test_build_encode_audio_for_uses_libfdk_aac_when_available(
    tmp_path: Path,
) -> None:
    """_build_encode_audio_for selects libfdk_aac when it is available."""
    # Arrange
    stream = _probed_audio_stream(tmp_path, codec_name="aac")

    # Act
    conversion_method = _build_encode_audio_for(stream, libfdk_aac_available=True)

    # Assert
    assert conversion_method.codec == "libfdk_aac"


@pytest.mark.unit
def test_build_encode_audio_for_warns_when_libfdk_aac_unavailable(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """_build_encode_audio_for warns and falls back to aac without libfdk_aac."""
    # Arrange
    mock_logger_warning = mocker.patch("ts2mp4.audio_encoder.logger.warning")
    stream = _probed_audio_stream(tmp_path, codec_name="aac")

    # Act
    conversion_method = _build_encode_audio_for(stream, libfdk_aac_available=False)

    # Assert
    assert conversion_method.codec == "aac"
    mock_logger_warning.assert_called_once_with(
        "libfdk_aac is not available. Falling back to the default AAC encoder."
    )


@pytest.mark.unit
def test_build_encode_audio_for_leaves_unknown_settings_unset(tmp_path: Path) -> None:
    """_build_encode_audio_for leaves settings the probe does not report as None."""
    # Arrange
    stream = _probed_audio_stream(tmp_path, codec_name="aac")

    # Act
    conversion_method = _build_encode_audio_for(stream, libfdk_aac_available=False)

    # Assert
    assert conversion_method == EncodeAudio(codec="aac")


@pytest.mark.unit
def test_build_encode_audio_for_raises_for_unsupported_codec(
    tmp_path: Path,
) -> None:
    """_build_encode_audio_for rejects codecs other than aac."""
    # Arrange
    stream = _probed_audio_stream(tmp_path, codec_name="mp3")

    # Act & Assert
    with pytest.raises(
        NotImplementedError,
        match="Encoding is currently only supported for aac audio codec.",
    ):
        _build_encode_audio_for(stream, libfdk_aac_available=False)


@pytest.mark.integration
def test_build_file_conversion_plan_for_audio_encoding_raises_for_missing_stream_in_real_file(
    tmp_path: Path, ts_file: Path
) -> None:
    """A real encoded file that lacks an original audio stream is rejected."""
    # Arrange
    original_video_file = VideoFile(path=ts_file)
    original_streams = original_video_file.streams

    encoded_file_path = tmp_path / "encoded_missing_stream.mp4"
    SubprocessFFmpegRunner().run(
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
        file_conversion_plan=FileConversionPlanForVideoEncoding(
            root=(
                StreamConversionPlan(
                    source_stream=stream_at(original_streams, 0),
                    conversion_method=EncodeVideo(
                        codec="libx265", crf=23, preset="medium"
                    ),
                ),
                StreamConversionPlan(
                    source_stream=stream_at(original_streams, 1),
                    conversion_method=Copy(),
                ),
            )
        ),
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="is missing a required stream"):
        build_file_conversion_plan_for_audio_encoding(
            original_file=original_video_file,
            encoded_file=encoded_video_file,
            integrity_report=IntegrityReport(mismatched_output_indices=frozenset({1})),
            libfdk_aac_available=False,
        )


@pytest.mark.unit
def test_file_conversion_plan_for_audio_encoding_validation_success(
    tmp_path: Path,
) -> None:
    """FileConversionPlanForAudioEncoding accepts a valid copied+encoded mix."""
    # Arrange
    dummy_original_file = tmp_path / "original.ts"
    dummy_original_file.touch()
    original_file = VideoFile(path=dummy_original_file)

    dummy_encoded_file = tmp_path / "encoded.mp4"
    dummy_encoded_file.touch()
    encoded_file = VideoFile(path=dummy_encoded_file)

    valid_plans: list[StreamConversionPlanForAudioEncoding] = [
        StreamConversionPlan(
            conversion_method=Copy(),
            source_stream=VideoStream(file=encoded_file, index=0),
        ),
        StreamConversionPlan(
            conversion_method=EncodeAudio(codec="aac"),
            source_stream=AudioStream(file=original_file, index=1),
        ),
    ]

    # Act & Assert
    FileConversionPlanForAudioEncoding(root=tuple(valid_plans))


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
def test_file_conversion_plan_for_audio_encoding_value_validation_failures(
    modifier: str, error_message: str, tmp_path: Path
) -> None:
    """Tests the validation rules in FileConversionPlanForAudioEncoding."""
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

    plans: list[StreamConversionPlanForAudioEncoding] = [
        StreamConversionPlan(
            conversion_method=Copy(),
            source_stream=VideoStream(file=encoded_file, index=0),
        ),
        StreamConversionPlan(
            conversion_method=Copy(),
            source_stream=AudioStream(file=encoded_file, index=1),
        ),
        StreamConversionPlan(
            conversion_method=EncodeAudio(codec="aac"),
            source_stream=AudioStream(file=original_file, index=2),
        ),
    ]

    if modifier == "no_video":
        plans = [s for s in plans if not isinstance(s.source_stream, VideoStream)]
    elif modifier == "video_from_original":
        plans[0] = StreamConversionPlan(
            source_stream=VideoStream(
                file=original_file, index=plans[0].source_stream.index
            ),
            conversion_method=plans[0].conversion_method,
        )
    elif modifier == "no_audio":
        plans = [s for s in plans if not isinstance(s.source_stream, AudioStream)]
    elif modifier == "copied_audio_from_original":
        plans.append(
            StreamConversionPlan(
                conversion_method=Copy(),
                source_stream=AudioStream(file=original_file, index=3),
            )
        )
    elif modifier == "encoded_audio_from_encoded":
        plans[2] = StreamConversionPlan(
            source_stream=AudioStream(
                file=encoded_file, index=plans[2].source_stream.index
            ),
            conversion_method=plans[2].conversion_method,
        )
    elif modifier == "only_encoded":
        plans = [plans[2]]
    elif modifier == "encoded_from_multiple":
        plans.append(
            StreamConversionPlan(
                conversion_method=EncodeAudio(codec="aac"),
                source_stream=AudioStream(file=another_original, index=3),
            )
        )

    # Act & Assert
    with pytest.raises(ValueError, match=error_message):
        FileConversionPlanForAudioEncoding(root=tuple(plans))


@pytest.mark.unit
@pytest.mark.parametrize(
    "stream_index_to_mismatch, mismatched_kind, expected_error_message_part",
    [
        (0, "audio", "expected to be 'video'"),
        (1, "video", "expected to be 'audio'"),
    ],
)
def test_build_file_conversion_plan_for_audio_encoding_stream_type_mismatch_raises_error(
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

    original_streams = mock_original_video_file.streams
    type(mock_encoded_video_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=tuple(
            StreamWithConversionPlan(
                stream=stream,
                conversion_plan=StreamConversionPlan(
                    source_stream=stream_at(original_streams, stream.index),
                    conversion_method=Copy(),
                ),
            )
            for stream in sorted(mismatched_streams, key=lambda s: s.index)
        )
    )

    # Act & Assert
    with pytest.raises(RuntimeError) as excinfo:
        build_file_conversion_plan_for_audio_encoding(
            mock_original_video_file,
            mock_encoded_video_file,
            IntegrityReport(mismatched_output_indices=frozenset({2})),
            libfdk_aac_available=False,
        )

    assert "Mismatch in stream types" in str(excinfo.value)
    assert expected_error_message_part in str(excinfo.value)
