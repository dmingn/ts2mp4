"""Unit tests for the stream_timing module."""

from fractions import Fraction
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import TS_TIME_BASE, StubVideoFile
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
from ts2mp4.ffprobe_schema import FFprobeFormat, FFprobeOutput, FFprobeStream
from ts2mp4.stream_timing import (
    CFR_VIDEO_END_TOLERANCE_SECONDS,
    TimingReport,
    check_timing,
)
from ts2mp4.video_file import AudioStream, VideoStream

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
        pytest.param(None, 0.5, frozenset(), id="unknown"),
    ],
)
def test_check_timing_compares_start_offset_of_encoded_audio(
    mocker: MockerFixture,
    tmp_path: Path,
    output_start_offset: float | None,
    source_start_offset: float | None,
    expected_shifted: frozenset[int],
) -> None:
    """check_timing reports re-encoded audio that starts at a different time.

    Start offsets may differ by the coarser time base of the two streams.
    """
    # Arrange
    converted_file = _converted_file(
        mocker,
        _audio_stream_with_plan(
            tmp_path,
            EncodeAudioWithNativeAac(),
            output_start_offset,
            source_start_offset,
        ),
    )

    # Act
    report = check_timing(converted_file)

    # Assert
    assert report == TimingReport(shifted_output_indices=expected_shifted)


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
    report = check_timing(converted_file)

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

    # Act
    report = check_timing(converted_file)

    # Assert
    assert report.is_ok


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
        check_timing(converted_file)
