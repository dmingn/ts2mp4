"""Tests for the conversion module."""

import io
import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from tests.helpers import FakeFFmpegRunner
from ts2mp4.conversion import execute_conversion
from ts2mp4.conversion_plan import Copy, FileConversionPlan, StreamConversionPlan
from ts2mp4.ffmpeg import SubprocessFFmpegRunner, execute_ffprobe
from ts2mp4.ffmpeg_input_args import build_input_args
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


class _TTYStringIO(io.StringIO):
    """A StringIO that reports itself as a TTY."""

    def isatty(self) -> bool:
        return True


@pytest.mark.unit
def test_execute_conversion_runs_ffmpeg_with_built_args(mocker: MockerFixture) -> None:
    """execute_conversion runs FFmpeg with the arguments built for the plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=())
    output_path = Path("output.mkv")
    ffmpeg_runner = FakeFFmpegRunner()

    mock_build_ffmpeg_args = mocker.patch(
        "ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"]
    )
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    execute_conversion(file_conversion_plan, output_path, ffmpeg_runner)

    # Assert
    mock_build_ffmpeg_args.assert_called_once_with(file_conversion_plan, output_path)
    assert ffmpeg_runner.calls == [["mock_arg"]]


@pytest.mark.unit
def test_execute_conversion_returns_converted_file_for_output(
    mocker: MockerFixture,
) -> None:
    """execute_conversion returns the output file paired with the plan."""
    # Arrange
    file_conversion_plan = FileConversionPlan(root=())
    output_path = Path("output.mkv")

    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mock_converted_video_file = mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    # Act
    converted_file = execute_conversion(
        file_conversion_plan, output_path, FakeFFmpegRunner()
    )

    # Assert
    mock_converted_video_file.assert_called_once_with(
        path=output_path, file_conversion_plan=file_conversion_plan
    )
    assert converted_file is mock_converted_video_file.return_value


@pytest.mark.unit
def test_execute_conversion_shows_progress_on_tty(mocker: MockerFixture) -> None:
    """execute_conversion shows the reported position on a TTY stderr."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [2.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mkv"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "Encoding: 2s" in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_caps_progress_at_source_duration(
    mocker: MockerFixture,
) -> None:
    """execute_conversion does not show progress beyond the source duration."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")
    mocker.patch.object(
        FileConversionPlan,
        "max_source_duration",
        new_callable=mocker.PropertyMock,
        return_value=3.0,
    )

    out_seconds = [3.6]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mkv"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "3/3" in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_does_not_show_negative_progress(
    mocker: MockerFixture,
) -> None:
    """execute_conversion does not move the progress below zero."""
    # Arrange
    stderr = _TTYStringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [-5.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mkv"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert "-5s" not in stderr.getvalue()


@pytest.mark.unit
def test_execute_conversion_shows_nothing_on_non_tty(mocker: MockerFixture) -> None:
    """execute_conversion does not show progress when stderr is not a TTY."""
    # Arrange
    stderr = io.StringIO()
    mocker.patch("sys.stderr", stderr)
    mocker.patch("ts2mp4.conversion.build_ffmpeg_args", return_value=["mock_arg"])
    mocker.patch("ts2mp4.conversion.ConvertedVideoFile")

    out_seconds = [2.0]

    # Act
    execute_conversion(
        FileConversionPlan(root=()),
        Path("output.mkv"),
        FakeFFmpegRunner(out_seconds=out_seconds),
    )

    # Assert
    assert stderr.getvalue() == ""


def _stream_start_times(path: Path) -> list[float]:
    """Return the start time in seconds of each stream of ``path``."""
    result = execute_ffprobe(
        [
            "-v",
            "error",
            "-show_entries",
            "stream=start_time",
            "-of",
            "json",
            *build_input_args(path),
        ]
    )
    return [
        float(stream["start_time"]) for stream in json.loads(result.stdout)["streams"]
    ]


@pytest.mark.integration
def test_execute_conversion_keeps_offsets_between_streams(
    ts_file: Path, tmp_path: Path
) -> None:
    """execute_conversion keeps the offset between streams read from separate inputs."""
    # Arrange
    delayed_audio_path = tmp_path / "delayed_audio.ts"
    SubprocessFFmpegRunner().run(
        [
            *build_input_args(ts_file),
            "-itsoffset",
            "0.5",
            *build_input_args(ts_file),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-f",
            "mpegts",
            str(delayed_audio_path),
        ]
    )
    source_video_start, source_audio_start = _stream_start_times(delayed_audio_path)

    source_file = VideoFile(path=delayed_audio_path)
    file_conversion_plan = FileConversionPlan(
        root=(
            StreamConversionPlan(
                source_stream=VideoStream(file=source_file, index=0),
                conversion_method=Copy(),
            ),
            StreamConversionPlan(
                source_stream=AudioStream(file=source_file, index=1),
                conversion_method=Copy(),
            ),
        )
    )

    # Act
    converted_file = execute_conversion(
        file_conversion_plan, tmp_path / "converted.mkv", SubprocessFFmpegRunner()
    )

    # Assert
    video_start, audio_start = _stream_start_times(converted_file.path)
    assert audio_start - video_start == pytest.approx(
        source_audio_start - source_video_start, abs=0.002
    )
