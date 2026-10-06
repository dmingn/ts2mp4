"""Unit tests for the stream_integrity module."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner, StubVideoFile
from ts2mp4.conversion_plan import (
    Copy,
    EncodeAudioWithNativeAac,
    EncodeVideo,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import ConvertedVideoFile, StreamWithConversionPlan
from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.stream_integrity import (
    IntegrityReport,
    check_integrity,
    compare_audio_parameters,
    compare_stream_hashes,
)
from ts2mp4.video_file import AudioStream, OtherStream, VideoFile, VideoStream

_FFMPEG_RUNNER = FakeFFmpegRunner()


@pytest.fixture
def input_video_file(tmp_path: Path) -> VideoFile:
    """Return an input VideoFile instance."""
    dummy_file = tmp_path / "dummy_input.ts"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.fixture
def output_video_file(tmp_path: Path) -> VideoFile:
    """Return an output VideoFile instance."""
    dummy_file = tmp_path / "dummy_output.mp4.part"
    dummy_file.touch()
    return VideoFile(path=dummy_file)


@pytest.mark.unit
def test_compare_stream_hashes_returns_true_when_hashes_match(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """compare_stream_hashes returns True when both MD5 hashes match."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", return_value="same_hash")

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
        _FFMPEG_RUNNER,
    )

    # Assert
    assert result is True


@pytest.mark.unit
def test_compare_stream_hashes_returns_false_when_hashes_differ(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """compare_stream_hashes returns False when MD5 hashes differ."""
    # Arrange
    mocker.patch(
        "ts2mp4.stream_integrity.get_stream_md5", side_effect=["hash1", "hash2"]
    )

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
        _FFMPEG_RUNNER,
    )

    # Assert
    assert result is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(RuntimeError("Mock error"), id="runtime_error"),
        pytest.param(
            FFmpegProcessError("ffmpeg failed with exit code 69"),
            id="ffmpeg_process_error",
        ),
    ],
)
def test_compare_stream_hashes_returns_false_when_hashing_fails(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
    error: Exception,
) -> None:
    """compare_stream_hashes returns False when get_stream_md5 raises."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.get_stream_md5", side_effect=error)

    # Act
    result = compare_stream_hashes(
        AudioStream(file=input_video_file, index=1),
        AudioStream(file=output_video_file, index=1),
        _FFMPEG_RUNNER,
    )

    # Assert
    assert result is False


_LC_STEREO_AAC = FFprobeStream(
    index=1,
    codec_type="audio",
    codec_name="aac",
    profile="LC",
    sample_rate=48000,
    channels=2,
)


def _stub_audio_stream(path: Path, probe_stream: FFprobeStream) -> AudioStream:
    """Return the AudioStream of a file at ``path`` that probes as ``probe_stream``."""
    path.touch()
    return AudioStream(
        file=StubVideoFile(
            path=path, stub_probe=FFprobeOutput(streams=(probe_stream,))
        ),
        index=probe_stream.index,
    )


@pytest.mark.unit
def test_compare_audio_parameters_returns_true_when_parameters_match(
    tmp_path: Path,
) -> None:
    """compare_audio_parameters returns True when the codec parameters match."""
    # Arrange
    stream_a = _stub_audio_stream(tmp_path / "a.ts", _LC_STEREO_AAC)
    stream_b = _stub_audio_stream(tmp_path / "b.mp4", _LC_STEREO_AAC)

    # Act
    result = compare_audio_parameters(stream_a, stream_b)

    # Assert
    assert result is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "probe_stream_b",
    [
        pytest.param(
            _LC_STEREO_AAC.model_copy(update={"profile": "-1"}),
            id="missing_decoder_configuration",
        ),
        pytest.param(
            _LC_STEREO_AAC.model_copy(
                update={"profile": "LTP", "sample_rate": 64000, "channels": 4}
            ),
            id="wrong_decoder_configuration",
        ),
        pytest.param(
            _LC_STEREO_AAC.model_copy(update={"codec_name": "mp3"}),
            id="different_codec",
        ),
    ],
)
def test_compare_audio_parameters_returns_false_when_parameters_differ(
    tmp_path: Path, probe_stream_b: FFprobeStream
) -> None:
    """compare_audio_parameters returns False when any codec parameter differs."""
    # Arrange
    stream_a = _stub_audio_stream(tmp_path / "a.ts", _LC_STEREO_AAC)
    stream_b = _stub_audio_stream(tmp_path / "b.mp4", probe_stream_b)

    # Act
    result = compare_audio_parameters(stream_a, stream_b)

    # Assert
    assert result is False


@pytest.fixture
def mock_converted_video_file(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> MagicMock:
    """Return a mocked ConvertedVideoFile instance."""
    input_streams = frozenset(
        (
            VideoStream(file=input_video_file, index=0),
            AudioStream(file=input_video_file, index=1),
        )
    )
    output_streams = frozenset(
        (
            VideoStream(file=output_video_file, index=0),
            AudioStream(file=output_video_file, index=1),
        )
    )

    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = output_video_file.path
    mock_converted_file.streams = output_streams
    mock_converted_file.file_conversion_plan = FileConversionPlan(
        root=(
            StreamConversionPlan(
                source_stream=next(s for s in input_streams if s.index == 0),
                conversion_method=EncodeVideo(codec="libsvtav1", crf=32, preset=5),
            ),
            StreamConversionPlan(
                source_stream=next(s for s in input_streams if s.index == 1),
                conversion_method=Copy(),
            ),
        )
    )

    # MagicMock doesn't automatically handle properties that are generators
    type(mock_converted_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=next(s for s in output_streams if s.index == i),
                conversion_plan=plan,
            )
            for i, plan in enumerate(mock_converted_file.file_conversion_plan)
        ]
    )

    return mock_converted_file


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mismatched_output_indices", "expected"),
    [
        pytest.param(frozenset(), True, id="no_mismatch"),
        pytest.param(frozenset({1}), False, id="with_mismatch"),
    ],
)
def test_integrity_report_is_ok(
    mismatched_output_indices: frozenset[int], expected: bool
) -> None:
    """IntegrityReport.is_ok is True only when no output index is mismatched."""
    # Arrange
    report = IntegrityReport(mismatched_output_indices=mismatched_output_indices)

    # Act
    result = report.is_ok

    # Assert
    assert result is expected


@pytest.mark.unit
def test_check_integrity_reports_no_mismatch_when_hashes_match(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """check_integrity reports no mismatch when copied stream hashes match."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.compare_audio_parameters", return_value=True)
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=True)

    # Act
    report = check_integrity(mock_converted_video_file, _FFMPEG_RUNNER)

    # Assert
    assert report == IntegrityReport(mismatched_output_indices=frozenset())


@pytest.mark.unit
def test_check_integrity_reports_mismatch_when_audio_parameters_differ(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
) -> None:
    """check_integrity reports a copied audio stream whose parameters differ.

    The MD5 hashes match, as they do for an AAC stream copied with its ADTS
    headers left in place.
    """
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.compare_audio_parameters", return_value=False)
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=True)

    # Act
    report = check_integrity(mock_converted_video_file, _FFMPEG_RUNNER)

    # Assert
    assert report == IntegrityReport(mismatched_output_indices=frozenset({1}))


@pytest.mark.unit
def test_check_integrity_reports_only_mismatched_output_indices(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """check_integrity reports mismatched copied streams by output index only."""
    # Arrange
    # Output and source indices of the audio streams are swapped on purpose so
    # that reporting the source index instead of the output index fails.
    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = output_video_file.path
    type(mock_converted_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=VideoStream(file=output_video_file, index=0),
                conversion_plan=StreamConversionPlan(
                    source_stream=VideoStream(file=input_video_file, index=0),
                    conversion_method=EncodeVideo(codec="libsvtav1", crf=32, preset=5),
                ),
            ),
            StreamWithConversionPlan(
                stream=AudioStream(file=output_video_file, index=1),
                conversion_plan=StreamConversionPlan(
                    source_stream=AudioStream(file=input_video_file, index=2),
                    conversion_method=Copy(),
                ),
            ),
            StreamWithConversionPlan(
                stream=AudioStream(file=output_video_file, index=2),
                conversion_plan=StreamConversionPlan(
                    source_stream=AudioStream(file=input_video_file, index=1),
                    conversion_method=Copy(),
                ),
            ),
        ]
    )
    mocker.patch("ts2mp4.stream_integrity.compare_audio_parameters", return_value=True)
    mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes",
        side_effect=lambda source_stream, _stream, _ffmpeg_runner: (
            source_stream.index == 2
        ),
    )

    # Act
    report = check_integrity(mock_converted_file, _FFMPEG_RUNNER)

    # Assert
    assert report == IntegrityReport(mismatched_output_indices=frozenset({2}))


@pytest.mark.unit
def test_check_integrity_compares_only_hashes_of_copied_video_streams(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """check_integrity compares copied video streams by hash, not audio parameters."""
    # Arrange
    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = output_video_file.path
    type(mock_converted_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=VideoStream(file=output_video_file, index=0),
                conversion_plan=StreamConversionPlan(
                    source_stream=VideoStream(file=input_video_file, index=0),
                    conversion_method=Copy(),
                ),
            ),
        ]
    )
    mock_compare_audio_parameters = mocker.patch(
        "ts2mp4.stream_integrity.compare_audio_parameters"
    )
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)

    # Act
    report = check_integrity(mock_converted_file, _FFMPEG_RUNNER)

    # Assert
    assert report == IntegrityReport(mismatched_output_indices=frozenset({0}))
    mock_compare_audio_parameters.assert_not_called()


@pytest.mark.unit
def test_check_integrity_raises_for_stream_type_mismatch(
    mocker: MockerFixture,
    input_video_file: VideoFile,
    output_video_file: VideoFile,
) -> None:
    """check_integrity raises ValueError when a copied stream changes its kind."""
    # Arrange
    mock_converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    mock_converted_file.path = output_video_file.path
    type(mock_converted_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=VideoStream(file=output_video_file, index=0),
                conversion_plan=StreamConversionPlan(
                    source_stream=AudioStream(file=input_video_file, index=0),
                    conversion_method=Copy(),
                ),
            ),
        ]
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Stream type mismatch"):
        check_integrity(mock_converted_file, _FFMPEG_RUNNER)


@pytest.mark.unit
def test_check_integrity_skips_non_copied_streams(
    mocker: MockerFixture, mock_converted_video_file: MagicMock
) -> None:
    """check_integrity does not compare hashes when no streams are copied."""
    # Arrange
    mock_compare_stream_hashes = mocker.patch(
        "ts2mp4.stream_integrity.compare_stream_hashes"
    )
    file_conversion_plan = list(mock_converted_video_file.file_conversion_plan)
    file_conversion_plan[1] = StreamConversionPlan(
        source_stream=file_conversion_plan[1].source_stream,
        conversion_method=EncodeAudioWithNativeAac(),
    )
    mock_converted_video_file.file_conversion_plan = FileConversionPlan(
        root=tuple(file_conversion_plan)
    )
    type(mock_converted_video_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=next(
                    s for s in mock_converted_video_file.streams if s.index == i
                ),
                conversion_plan=plan,
            )
            for i, plan in enumerate(mock_converted_video_file.file_conversion_plan)
        ]
    )

    # Act
    check_integrity(mock_converted_video_file, _FFMPEG_RUNNER)

    # Assert
    mock_compare_stream_hashes.assert_not_called()


@pytest.mark.unit
def test_check_integrity_raises_for_unsupported_stream_type(
    mocker: MockerFixture,
    mock_converted_video_file: MagicMock,
    output_video_file: VideoFile,
) -> None:
    """check_integrity raises NotImplementedError for non-A/V copied streams."""
    # Arrange
    mocker.patch("ts2mp4.stream_integrity.compare_stream_hashes", return_value=False)
    mock_converted_video_file.streams = frozenset(
        OtherStream(file=output_video_file, index=1) if stream.index == 1 else stream
        for stream in mock_converted_video_file.streams
    )
    type(mock_converted_video_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[
            StreamWithConversionPlan(
                stream=next(
                    s for s in mock_converted_video_file.streams if s.index == i
                ),
                conversion_plan=plan,
            )
            for i, plan in enumerate(mock_converted_video_file.file_conversion_plan)
        ]
    )

    # Act & Assert
    with pytest.raises(
        NotImplementedError,
        match="Stream integrity check for non-audio/video streams is not implemented.",
    ):
        check_integrity(mock_converted_video_file, _FFMPEG_RUNNER)
