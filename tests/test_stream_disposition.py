"""Unit tests for stream disposition selection."""

from pathlib import Path
from typing import NamedTuple

import pytest
from pytest_mock import MockerFixture

from tests.helpers import StubVideoFile
from ts2mp4.ffprobe_schema import FFprobeFormat, FFprobeOutput, FFprobeStream
from ts2mp4.stream_disposition import (
    build_disposition_args,
    get_default_stream_indices,
)
from ts2mp4.stream_source import (
    Conversion,
    Copy,
    EncodeVideo,
    StreamSource,
    StreamSources,
)
from ts2mp4.video_file import AudioStream, Stream, VideoStream


class _StreamSpec(NamedTuple):
    """Probe fields for one stream in disposition selection cases."""

    codec_type: str
    stream_index: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None


def _conversion_for_stream(stream: Stream) -> Conversion:
    """Return a conversion suitable for StreamSource construction in tests."""
    if isinstance(stream, VideoStream):
        return EncodeVideo()
    return Copy()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stream_specs", "format_duration", "expected"),
    [
        pytest.param(
            (
                _StreamSpec("video", 0, width=720, height=480, duration=6.657),
                _StreamSpec("video", 1, width=1440, height=1080, duration=2407.0),
                _StreamSpec("audio", 2, duration=2400.0),
            ),
            2407.0,
            frozenset({1, 2}),
            id="prefers_longer_video_over_short_remnant",
        ),
        pytest.param(
            (
                _StreamSpec("video", 0, width=720, height=480, duration=1807.0),
                _StreamSpec("video", 1, width=1440, height=1080, duration=1808.0),
                _StreamSpec("audio", 2, duration=1807.0),
            ),
            1808.0,
            frozenset({1, 2}),
            id="prefers_higher_resolution_when_both_span",
        ),
        pytest.param(
            (
                _StreamSpec("video", 0, width=1440, height=1080, duration=2407.0),
                _StreamSpec("audio", 1, duration=6.464),
                _StreamSpec("audio", 2, duration=2400.0),
            ),
            2407.0,
            frozenset({0, 2}),
            id="prefers_longer_audio_over_short_remnant",
        ),
        pytest.param(
            (
                _StreamSpec("video", 0, width=720, height=480),
                _StreamSpec("video", 1, width=1440, height=1080, duration=2400.0),
                _StreamSpec("audio", 2),
                _StreamSpec("audio", 3, duration=2400.0),
            ),
            2407.0,
            frozenset({1, 3}),
            id="prefers_known_duration_over_missing",
        ),
        pytest.param(
            (
                _StreamSpec("video", 0, width=720, height=480, duration=100.0),
                _StreamSpec("video", 1, width=720, height=480, duration=100.0),
                _StreamSpec("audio", 2, duration=100.0),
                _StreamSpec("audio", 3, duration=100.0),
            ),
            100.0,
            frozenset({0, 2}),
            id="breaks_ties_by_earlier_output_index",
        ),
        pytest.param(
            (
                _StreamSpec("video", 0),
                _StreamSpec("video", 1),
                _StreamSpec("audio", 2),
                _StreamSpec("audio", 3),
            ),
            None,
            frozenset({0, 2}),
            id="falls_back_to_first_when_duration_missing",
        ),
    ],
)
def test_get_default_stream_indices(
    tmp_path: Path,
    stream_specs: tuple[_StreamSpec, ...],
    format_duration: float | None,
    expected: frozenset[int],
) -> None:
    """Select the primary video and audio stream indices for disposition default."""
    # Arrange
    source_path = tmp_path / "input.ts"
    source_path.touch()
    video_file = StubVideoFile(
        path=source_path,
        stub_probe=FFprobeOutput(
            streams=tuple(
                FFprobeStream(
                    codec_type=spec.codec_type,
                    index=spec.stream_index,
                    width=spec.width,
                    height=spec.height,
                    duration=spec.duration,
                )
                for spec in stream_specs
            ),
            format=FFprobeFormat(duration=format_duration),
        ),
    )
    stream_sources = StreamSources(
        root=tuple(
            StreamSource(
                source_stream=stream,
                conversion=_conversion_for_stream(stream),
            )
            for stream in sorted(video_file.streams)
        )
    )

    # Act
    result = get_default_stream_indices(stream_sources)

    # Assert
    assert result == expected


@pytest.mark.unit
def test_build_disposition_args_marks_only_defaults(mocker: MockerFixture) -> None:
    """Build FFmpeg args that mark only the primary streams as default."""
    # Arrange
    stream_sources = mocker.MagicMock(spec=StreamSources)
    stream_sources.__len__.return_value = 3
    mocker.patch(
        "ts2mp4.stream_disposition.get_default_stream_indices",
        return_value=frozenset({0, 2}),
    )

    # Act
    result = build_disposition_args(stream_sources)

    # Assert
    assert result == [
        "-disposition:0",
        "default",
        "-disposition:1",
        "0",
        "-disposition:2",
        "default",
    ]


@pytest.mark.unit
def test_get_default_stream_indices_uses_each_source_video_file_for_container_duration(
    tmp_path: Path,
) -> None:
    """Look up container duration from each source stream's own video file."""
    # Arrange
    # path_a: short container so a low-res video that fills it spans.
    # path_b: long container so a high-res video of the same stream length does not.
    # If every stream wrongly used one path's container, resolution would pick index 1.
    path_a = tmp_path / "a.mp4"
    path_b = tmp_path / "b.ts"
    path_a.touch()
    path_b.touch()
    file_a = StubVideoFile(
        path=path_a,
        stub_probe=FFprobeOutput(
            format=FFprobeFormat(duration=100.0),
            streams=(
                FFprobeStream(
                    index=0, codec_type="video", width=720, height=480, duration=100.0
                ),
                FFprobeStream(index=2, codec_type="audio", duration=100.0),
            ),
        ),
    )
    file_b = StubVideoFile(
        path=path_b,
        stub_probe=FFprobeOutput(
            format=FFprobeFormat(duration=1000.0),
            streams=(
                FFprobeStream(
                    index=0,
                    codec_type="video",
                    width=1440,
                    height=1080,
                    duration=100.0,
                ),
            ),
        ),
    )

    low_res_video = VideoStream(file=file_a, index=0)
    high_res_video = VideoStream(file=file_b, index=0)
    audio = AudioStream(file=file_a, index=2)

    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=low_res_video,
                conversion=Copy(),
            ),
            StreamSource(
                source_stream=high_res_video,
                conversion=EncodeVideo(),
            ),
            StreamSource(
                source_stream=audio,
                conversion=Copy(),
            ),
        )
    )

    # Act
    result = get_default_stream_indices(stream_sources)

    # Assert
    assert result == frozenset({0, 2})
