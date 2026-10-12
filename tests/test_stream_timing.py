"""Unit tests for the stream_timing module."""

from fractions import Fraction
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import TS_TIME_BASE, FakeFFmpegRunner, StubVideoFile
from ts2mp4.conversion_plan import (
    ConversionMethod,
    Copy,
    EncodeAudioWithNativeAac,
    EncodeVideo,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import (
    AnyStreamWithConversionPlan,
    ConvertedVideoFile,
    StreamWithConversionPlan,
)
from ts2mp4.ffmpeg import FFmpegProcessError
from ts2mp4.ffmpeg_input_args import build_zero_based_input_args
from ts2mp4.ffprobe_schema import FFprobeFormat, FFprobeOutput, FFprobeStream
from ts2mp4.stream_timing import (
    CFR_VIDEO_END_TOLERANCE_SECONDS,
    TimingReport,
    check_timing,
    first_decoded_pts,
)
from ts2mp4.video_file import AudioStream, VideoStream

_FRAMEMD5_OUTPUT = b"""#format: frame checksums
#version: 2
#hash: MD5
#tb 0: 1/48000
#stream#, dts,        pts, duration,     size, hash
0,       1024,       1024,     1024,     4096, 979d1739445970f12da5a7fc215b75b4
"""

_ENCODE_VIDEO = EncodeVideo(codec="libsvtav1", crf=32, preset=5, fps_mode="cfr")

_MKV_TIME_BASE = Fraction(1, 1000)
_AUDIO_START_TOLERANCE = float(_MKV_TIME_BASE)


def _stub_file(
    path: Path,
    codec_type: str,
    start_time: float | None,
    duration: float | None,
    time_base: Fraction,
) -> StubVideoFile:
    """Return a file starting at zero whose only stream has the given timing."""
    path.touch()
    return StubVideoFile(
        path=path,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(
                    index=0,
                    codec_type=codec_type,
                    time_base=time_base,
                    start_time=start_time,
                    duration=duration,
                ),
            ),
            format=FFprobeFormat(start_time=0.0),
        ),
    )


def _audio_stream_with_plan(
    tmp_path: Path,
    conversion_method: ConversionMethod,
    output_start_offset: float | None,
    source_start_offset: float | None,
) -> AnyStreamWithConversionPlan:
    """Return an output audio stream paired with a plan from a source stream."""
    return StreamWithConversionPlan(
        stream=AudioStream(
            file=_stub_file(
                tmp_path / "out.mkv",
                "audio",
                output_start_offset,
                10.0,
                _MKV_TIME_BASE,
            ),
            index=0,
        ),
        conversion_plan=StreamConversionPlan(
            source_stream=AudioStream(
                file=_stub_file(
                    tmp_path / "in.ts",
                    "audio",
                    source_start_offset,
                    10.0,
                    TS_TIME_BASE,
                ),
                index=0,
            ),
            conversion_method=conversion_method,
        ),
    )


def _video_stream_with_plan(
    tmp_path: Path,
    output_end_offset: float | None,
    source_end_offset: float | None,
    encode_video: EncodeVideo = _ENCODE_VIDEO,
) -> AnyStreamWithConversionPlan:
    """Return a re-encoded output video stream starting at zero, like its source."""
    return StreamWithConversionPlan(
        stream=VideoStream(
            file=_stub_file(
                tmp_path / "out.mkv", "video", 0.0, output_end_offset, _MKV_TIME_BASE
            ),
            index=0,
        ),
        conversion_plan=StreamConversionPlan(
            source_stream=VideoStream(
                file=_stub_file(
                    tmp_path / "in.ts", "video", 0.0, source_end_offset, TS_TIME_BASE
                ),
                index=0,
            ),
            conversion_method=encode_video,
        ),
    )


def _converted_file(
    mocker: MockerFixture, stream_with_conversion_plan: AnyStreamWithConversionPlan
) -> MagicMock:
    """Return a converted file whose only output stream is the given one."""
    converted_file = cast(MagicMock, mocker.MagicMock(spec=ConvertedVideoFile))
    type(converted_file).streams_with_conversion_plans = mocker.PropertyMock(
        return_value=[stream_with_conversion_plan]
    )
    return converted_file


@pytest.mark.unit
@pytest.mark.parametrize(
    "output_start_offset, source_start_offset, expected_shifted",
    [
        pytest.param(0.5, 0.5, frozenset(), id="same"),
        pytest.param(
            0.5 + _AUDIO_START_TOLERANCE / 2,
            0.5,
            frozenset(),
            id="within_tolerance",
        ),
        pytest.param(
            0.5 + _AUDIO_START_TOLERANCE * 2,
            0.5,
            frozenset({0}),
            id="shifted",
        ),
    ],
)
def test_check_timing_compares_start_offset_of_encoded_audio(
    mocker: MockerFixture,
    tmp_path: Path,
    output_start_offset: float,
    source_start_offset: float,
    expected_shifted: frozenset[int],
) -> None:
    """check_timing reports re-encoded audio whose first decoded sample differs.

    The container start time is ignored. The decoded timestamps may differ by
    the coarser time base of the two streams.
    """
    # Arrange
    stream_with_plan = _audio_stream_with_plan(
        tmp_path, EncodeAudioWithNativeAac(), 0.0, 10.0
    )
    converted_file = _converted_file(mocker, stream_with_plan)
    decoded_pts = mocker.patch(
        "ts2mp4.stream_timing.first_decoded_pts",
        side_effect=[output_start_offset, source_start_offset],
    )

    # Act
    report = check_timing(converted_file, FakeFFmpegRunner())

    # Assert
    assert report == TimingReport(shifted_output_indices=expected_shifted)
    assert [call.args[0] for call in decoded_pts.call_args_list] == [
        stream_with_plan.stream,
        stream_with_plan.conversion_plan.source_stream,
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("output_start_offset", "source_start_offset"),
    [
        pytest.param(None, 0.5, id="output"),
        pytest.param(0.5, None, id="source"),
    ],
)
def test_check_timing_raises_when_the_first_decoded_sample_is_missing(
    mocker: MockerFixture,
    tmp_path: Path,
    output_start_offset: float | None,
    source_start_offset: float | None,
) -> None:
    """check_timing raises when either re-encoded audio stream has no decoded sample."""
    # Arrange
    converted_file = _converted_file(
        mocker,
        _audio_stream_with_plan(tmp_path, EncodeAudioWithNativeAac(), 0.0, 10.0),
    )
    mocker.patch(
        "ts2mp4.stream_timing.first_decoded_pts",
        side_effect=[output_start_offset, source_start_offset],
    )

    # Act & Assert
    with pytest.raises(RuntimeError, match="Could not read the first decoded sample"):
        check_timing(converted_file, FakeFFmpegRunner())


@pytest.mark.unit
@pytest.mark.parametrize(
    "output_end_offset, source_end_offset, expected_shifted",
    [
        pytest.param(30.0, 30.0, frozenset(), id="same"),
        pytest.param(
            30.0 + CFR_VIDEO_END_TOLERANCE_SECONDS / 2,
            30.0,
            frozenset(),
            id="within_tolerance",
        ),
        pytest.param(
            30.0 - CFR_VIDEO_END_TOLERANCE_SECONDS * 2,
            30.0,
            frozenset({0}),
            id="shifted",
        ),
        pytest.param(None, 30.0, frozenset(), id="unknown"),
    ],
)
def test_check_timing_compares_end_offset_of_cfr_encoded_video(
    mocker: MockerFixture,
    tmp_path: Path,
    output_end_offset: float | None,
    source_end_offset: float | None,
    expected_shifted: frozenset[int],
) -> None:
    """check_timing reports cfr re-encoded video that ends at a different time."""
    # Arrange
    converted_file = _converted_file(
        mocker, _video_stream_with_plan(tmp_path, output_end_offset, source_end_offset)
    )

    # Act
    report = check_timing(converted_file, FakeFFmpegRunner())

    # Assert
    assert report == TimingReport(shifted_output_indices=expected_shifted)


@pytest.mark.unit
def test_check_timing_leaves_copied_streams_to_the_integrity_check(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """check_timing does not judge copied streams, even if they start elsewhere."""
    # Arrange
    converted_file = _converted_file(
        mocker, _audio_stream_with_plan(tmp_path, Copy(), 0.0, 0.5)
    )
    decoded_pts = mocker.patch("ts2mp4.stream_timing.first_decoded_pts")

    # Act
    report = check_timing(converted_file, FakeFFmpegRunner())

    # Assert
    assert report.is_ok
    decoded_pts.assert_not_called()


@pytest.mark.unit
def test_check_timing_raises_for_video_not_encoded_with_cfr(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """check_timing raises NotImplementedError for video encoded without cfr."""
    # Arrange
    converted_file = _converted_file(
        mocker,
        _video_stream_with_plan(
            tmp_path,
            30.0,
            30.0,
            _ENCODE_VIDEO.model_copy(update={"fps_mode": "passthrough"}),
        ),
    )

    # Act & Assert
    with pytest.raises(NotImplementedError, match="fps_mode passthrough"):
        check_timing(converted_file, FakeFFmpegRunner())


def _audio_stream(tmp_path: Path, start_time: float) -> AudioStream:
    """Return an audio stream of an empty file whose container starts at ``start_time``."""
    return AudioStream(
        file=_stub_file(tmp_path / "audio.ts", "audio", start_time, 10.0, TS_TIME_BASE),
        index=2,
    )


@pytest.mark.unit
def test_first_decoded_pts_reads_the_first_frame_from_the_file_start(
    tmp_path: Path,
) -> None:
    """first_decoded_pts returns the first framemd5 timestamp, in seconds."""
    # Arrange
    stream = _audio_stream(tmp_path, 100.0)
    ffmpeg_runner = FakeFFmpegRunner(stdout=_FRAMEMD5_OUTPUT)

    # Act
    pts = first_decoded_pts(stream, ffmpeg_runner)

    # Assert
    assert pts == pytest.approx(1024 / 48000)
    (args,) = ffmpeg_runner.calls
    input_args = build_zero_based_input_args(stream.file.path, stream.file.start_time)
    assert args[:3] == ["-hide_banner", "-nostats", "-copyts"]
    assert any(args[i : i + len(input_args)] == input_args for i in range(len(args)))
    assert any(args[i : i + 2] == ["-map", "0:2"] for i in range(len(args)))
    assert any(args[i : i + 2] == ["-frames:a", "1"] for i in range(len(args)))


@pytest.mark.unit
def test_first_decoded_pts_is_unknown_when_no_frame_decodes(tmp_path: Path) -> None:
    """first_decoded_pts returns None when ffmpeg emits no frame."""
    # Arrange
    stream = _audio_stream(tmp_path, 0.0)
    ffmpeg_runner = FakeFFmpegRunner(stdout=b"#tb 0: 1/48000\n")

    # Act
    pts = first_decoded_pts(stream, ffmpeg_runner)

    # Assert
    assert pts is None


@pytest.mark.unit
def test_first_decoded_pts_is_unknown_without_framemd5_output(tmp_path: Path) -> None:
    """first_decoded_pts returns None when ffmpeg emits no framemd5 header."""
    # Arrange
    stream = _audio_stream(tmp_path, 0.0)

    # Act
    pts = first_decoded_pts(stream, FakeFFmpegRunner(stdout=b""))

    # Assert
    assert pts is None


@pytest.mark.unit
def test_first_decoded_pts_raises_on_ffmpeg_failure(tmp_path: Path) -> None:
    """first_decoded_pts raises FFmpegProcessError when ffmpeg fails."""
    # Arrange
    stream = _audio_stream(tmp_path, 0.0)
    ffmpeg_runner = FakeFFmpegRunner(error=FFmpegProcessError("ffmpeg failed"))

    # Act & Assert
    with pytest.raises(FFmpegProcessError, match="ffmpeg failed"):
        first_decoded_pts(stream, ffmpeg_runner)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("output_is_audio", "source_is_audio"),
    [
        pytest.param(False, True, id="output"),
        pytest.param(True, False, id="source"),
    ],
)
def test_check_timing_rejects_a_non_audio_stream_encoded_as_audio(
    mocker: MockerFixture,
    tmp_path: Path,
    output_is_audio: bool,
    source_is_audio: bool,
) -> None:
    """check_timing raises when an audio encoding plan is paired with video."""
    # Arrange
    output_type = AudioStream if output_is_audio else VideoStream
    source_type = AudioStream if source_is_audio else VideoStream
    converted_file = _converted_file(
        mocker,
        StreamWithConversionPlan(
            stream=output_type(
                file=_stub_file(
                    tmp_path / "out.mkv",
                    "audio" if output_is_audio else "video",
                    0.0,
                    10.0,
                    _MKV_TIME_BASE,
                ),
                index=0,
            ),
            conversion_plan=StreamConversionPlan(
                source_stream=source_type(
                    file=_stub_file(
                        tmp_path / "in.ts",
                        "audio" if source_is_audio else "video",
                        0.0,
                        10.0,
                        TS_TIME_BASE,
                    ),
                    index=0,
                ),
                conversion_method=EncodeAudioWithNativeAac(),
            ),
        ),
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Stream type mismatch"):
        check_timing(converted_file, FakeFFmpegRunner())
