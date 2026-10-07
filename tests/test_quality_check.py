"""Unit and integration tests for the quality_check module."""

import asyncio
import math
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.conversion import execute_conversion
from ts2mp4.conversion_plan import (
    ConversionMethod,
    Copy,
    EncodeAudioWithNativeAac,
    FileConversionPlan,
    StreamConversionPlan,
)
from ts2mp4.converted_video_file import ConvertedVideoFile, StreamWithConversionPlan
from ts2mp4.ffmpeg import FFmpegProcessError, SubprocessFFmpegRunner
from ts2mp4.ffmpeg_input_args import build_input_args
from ts2mp4.quality_check import (
    ASDR_THRESHOLD_DB,
    AudioQualityReport,
    build_comparison_args,
    build_reference_args,
    check_audio_quality,
    get_asdr,
    parse_asdr,
)
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


async def _lines(ffmpeg_output: str) -> AsyncGenerator[str, None]:
    for line in ffmpeg_output.splitlines():
        yield line


def _converted_file_with_audio_streams(
    tmp_path: Path, conversion_method: ConversionMethod
) -> MagicMock:
    """Return a converted file whose streams 0 and 2 are audio and 1 is copied video."""
    (tmp_path / "original.ts").touch()
    (tmp_path / "converted.mp4").touch()
    original_file = VideoFile(path=tmp_path / "original.ts")
    converted_video = VideoFile(path=tmp_path / "converted.mp4")

    mock_converted_file = MagicMock(spec=ConvertedVideoFile)
    mock_converted_file.streams_with_conversion_plans = [
        StreamWithConversionPlan(
            stream=AudioStream(file=converted_video, index=0),
            conversion_plan=StreamConversionPlan(
                conversion_method=conversion_method,
                source_stream=AudioStream(file=original_file, index=3),
            ),
        ),
        StreamWithConversionPlan(
            stream=VideoStream(file=converted_video, index=1),
            conversion_plan=StreamConversionPlan(
                conversion_method=Copy(),
                source_stream=VideoStream(file=original_file, index=4),
            ),
        ),
        StreamWithConversionPlan(
            stream=AudioStream(file=converted_video, index=2),
            conversion_plan=StreamConversionPlan(
                conversion_method=conversion_method,
                source_stream=AudioStream(file=original_file, index=5),
            ),
        ),
    ]
    mock_converted_file.path = converted_video.path

    return mock_converted_file


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ffmpeg_output, expected",
    [
        pytest.param(
            "[Parsed_asdr_0 @ 0x7f9990004ac0] SDR ch0: inf dB",
            (float("inf"),),
            id="infinite_value",
        ),
        pytest.param(
            "[Parsed_asdr_0 @ 0x7f9990004ac0] SDR ch0: -5.25 dB",
            (-5.25,),
            id="negative_value",
        ),
        pytest.param(
            "[Parsed_asdr_0 @ 0x123] SDR ch0: 10.0 dB\n"
            "[Parsed_asdr_0 @ 0x123] SDR ch1: 20.0 dB",
            (10.0, 20.0),
            id="channels_in_order",
        ),
        pytest.param(
            "No metrics here",
            (),
            id="no_metrics",
        ),
        pytest.param(
            "[Parsed_asdr_0 @ 0x123] SDR ch0: invalid dB",
            (),
            id="unparsable_value",
        ),
    ],
)
async def test_parse_asdr(ffmpeg_output: str, expected: tuple[float, ...]) -> None:
    """parse_asdr reads the ASDR of every channel."""
    # Act
    asdr = await parse_asdr(_lines(ffmpeg_output))

    # Assert
    assert asdr == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_asdr_reads_negative_nan_as_nan() -> None:
    """parse_asdr reads FFmpeg's -nan as NaN."""
    # Act
    asdr = await parse_asdr(_lines("[Parsed_asdr_0 @ 0x7f9990004ac0] SDR ch0: -nan dB"))

    # Assert
    assert math.isnan(asdr[0])


@pytest.mark.unit
@pytest.mark.parametrize(
    "asdr, expected",
    [
        pytest.param((30.0, ASDR_THRESHOLD_DB), frozenset(), id="all_at_or_above"),
        pytest.param((30.0, ASDR_THRESHOLD_DB - 0.01), frozenset({1}), id="one_below"),
        pytest.param((30.0, float("nan")), frozenset(), id="nan_ignored"),
        pytest.param((30.0, float("-inf")), frozenset({1}), id="negative_infinity"),
        pytest.param((), frozenset({1}), id="no_channel"),
    ],
)
def test_audio_quality_report_degraded_output_indices(
    asdr: tuple[float, ...], expected: frozenset[int]
) -> None:
    """A stream is degraded unless every measured channel reaches the ASDR threshold."""
    # Arrange
    report = AudioQualityReport(asdr_by_output_index={1: asdr})

    # Act
    degraded_output_indices = report.degraded_output_indices

    # Assert
    assert degraded_output_indices == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "asdr, expected",
    [
        pytest.param((30.0,), True, id="no_degraded_stream"),
        pytest.param((-3.0,), False, id="degraded_stream"),
    ],
)
def test_audio_quality_report_is_ok(asdr: tuple[float, ...], expected: bool) -> None:
    """is_ok is True only when no stream is degraded."""
    # Arrange
    report = AudioQualityReport(asdr_by_output_index={1: asdr})

    # Act & Assert
    assert report.is_ok is expected


@pytest.mark.unit
def test_build_reference_args_writes_stream_to_stdout_as_pcm() -> None:
    """build_reference_args maps the stream and writes it to stdout as PCM in NUT."""
    # Act
    args = build_reference_args(Path("original.ts"), 3, None)

    # Assert
    assert args == [
        "-hide_banner",
        "-nostats",
        *build_input_args(Path("original.ts")),
        "-map",
        "0:3",
        "-c:a",
        "pcm_f32le",
        "-f",
        "nut",
        "pipe:1",
    ]


@pytest.mark.unit
def test_build_reference_args_applies_audio_filter() -> None:
    """build_reference_args applies audio_filter to the stream."""
    # Act
    args = build_reference_args(Path("original.ts"), 3, "aformat=channel_layouts=5.1")

    # Assert
    assert args[args.index("-af") + 1] == "aformat=channel_layouts=5.1"


@pytest.mark.unit
def test_build_comparison_args_compares_stdin_with_re_encoded_stream() -> None:
    """build_comparison_args feeds the PCM from stdin and the re-encoded stream to asdr."""
    # Act
    args = build_comparison_args(Path("converted.mp4"), 2)

    # Assert
    assert args == [
        "-hide_banner",
        "-nostats",
        "-f",
        "nut",
        "-i",
        "pipe:0",
        *build_input_args(Path("converted.mp4")),
        "-filter_complex",
        "[0:0][1:2]asdr",
        "-f",
        "null",
        "-",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_asdr_returns_asdr_of_encoded_audio(
    tmp_path: Path,
) -> None:
    """Return the ASDR of each encoded audio stream and skip copied streams."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(
        stderr_lines=["[Parsed_asdr_0 @ 0x456] SDR ch0: 25.00 dB"]
    )
    converted_file = _converted_file_with_audio_streams(
        tmp_path, EncodeAudioWithNativeAac()
    )

    # Act
    asdr_by_output_index = await get_asdr(converted_file, ffmpeg_runner)

    # Assert
    assert asdr_by_output_index == {0: (25.0,), 2: (25.0,)}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_asdr_logs_asdr_of_each_stream(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Log one audio quality line per re-encoded stream."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(
        stderr_lines=[
            "[Parsed_asdr_0 @ 0x456] SDR ch0: 30.00 dB",
            "[Parsed_asdr_0 @ 0x456] SDR ch1: 31.50 dB",
        ]
    )
    converted_file = _converted_file_with_audio_streams(
        tmp_path, EncodeAudioWithNativeAac()
    )
    mock_logger_info = mocker.patch("ts2mp4.quality_check.logger.info")

    # Act
    await get_asdr(converted_file, ffmpeg_runner)

    # Assert
    assert [call.args[0] for call in mock_logger_info.call_args_list] == [
        "Audio quality for stream 0: ASDR=[30.00, 31.50]dB",
        "Audio quality for stream 2: ASDR=[30.00, 31.50]dB",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_asdr_pipes_source_stream_into_comparison(
    tmp_path: Path,
) -> None:
    """Pipe each source stream, through its audio filter, into the comparison."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner()
    converted_file = _converted_file_with_audio_streams(
        tmp_path, EncodeAudioWithNativeAac(audio_filter="aformat=channel_layouts=5.1")
    )

    # Act
    await get_asdr(converted_file, ffmpeg_runner)

    # Assert
    assert ffmpeg_runner.piped_calls == [
        (
            build_reference_args(
                tmp_path / "original.ts", 3, "aformat=channel_layouts=5.1"
            ),
            build_comparison_args(tmp_path / "converted.mp4", 0),
        ),
        (
            build_reference_args(
                tmp_path / "original.ts", 5, "aformat=channel_layouts=5.1"
            ),
            build_comparison_args(tmp_path / "converted.mp4", 2),
        ),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_asdr_raises_when_ffmpeg_fails(
    tmp_path: Path,
) -> None:
    """Propagate FFmpegProcessError so that an unverified stream is not accepted."""
    # Arrange
    ffmpeg_runner = FakeFFmpegRunner(error=FFmpegProcessError("Error"))
    converted_file = _converted_file_with_audio_streams(
        tmp_path, EncodeAudioWithNativeAac()
    )

    # Act & Assert
    with pytest.raises(FFmpegProcessError):
        await get_asdr(converted_file, ffmpeg_runner)


@pytest.mark.unit
def test_check_audio_quality_reports_asdr_of_each_stream(
    mocker: MockerFixture,
) -> None:
    """check_audio_quality wraps the ASDR of each stream in a report."""
    # Arrange
    asdr_by_output_index = {1: (30.0,)}
    mocker.patch(
        "ts2mp4.quality_check.get_asdr",
        return_value=asdr_by_output_index,
    )

    # Act
    report = check_audio_quality(MagicMock(spec=ConvertedVideoFile), FakeFFmpegRunner())

    # Assert
    assert report == AudioQualityReport(asdr_by_output_index=asdr_by_output_index)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_asdr_meets_threshold_for_identical_file(
    ts_file: Path,
) -> None:
    """Meet the threshold for every valid audio stream compared with itself."""
    # Arrange
    video_file = VideoFile(path=ts_file)
    file_conversion_plan: list[StreamConversionPlan[Stream, ConversionMethod]] = []
    for stream in sorted(video_file.streams):
        if isinstance(stream, AudioStream):
            conversion_method: ConversionMethod = EncodeAudioWithNativeAac()
        else:
            conversion_method = Copy()
        file_conversion_plan.append(
            StreamConversionPlan(
                source_stream=stream,
                conversion_method=conversion_method,
            )
        )

    converted_file = ConvertedVideoFile[FileConversionPlan](
        path=ts_file,
        file_conversion_plan=FileConversionPlan(root=tuple(file_conversion_plan)),
    )

    # Act
    asdr_by_output_index = await get_asdr(converted_file, SubprocessFFmpegRunner())

    # Assert
    assert asdr_by_output_index.keys() == {
        s.index for s in video_file.valid_audio_streams
    }
    assert AudioQualityReport(asdr_by_output_index=asdr_by_output_index).is_ok


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_asdr_meets_threshold_across_channel_layout_change(
    tmp_path: Path, mixed_surround_ts_file: Path
) -> None:
    """Meet the threshold on every 5.1ch channel for audio switching from stereo."""
    # Arrange
    ffmpeg_runner = SubprocessFFmpegRunner()
    original_file = VideoFile(path=mixed_surround_ts_file)
    converted_file = await asyncio.to_thread(
        execute_conversion,
        FileConversionPlan(
            root=(
                StreamConversionPlan(
                    source_stream=VideoStream(file=original_file, index=0),
                    conversion_method=Copy(),
                ),
                StreamConversionPlan(
                    source_stream=AudioStream(file=original_file, index=1),
                    conversion_method=EncodeAudioWithNativeAac(
                        channels=6,
                        audio_filter="aformat=channel_layouts=5.1",
                    ),
                ),
            )
        ),
        tmp_path / "converted.mp4",
        ffmpeg_runner,
    )

    # Act
    asdr_by_output_index = await get_asdr(converted_file, ffmpeg_runner)

    # Assert
    assert len(asdr_by_output_index[1]) == 6
    assert AudioQualityReport(asdr_by_output_index=asdr_by_output_index).is_ok
