"""Unit tests for stream disposition selection."""

from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffprobe_schema import FFprobeFormat, FFprobeOutput
from ts2mp4.stream_disposition import (
    build_disposition_args,
    get_default_stream_indices,
)
from ts2mp4.stream_source import ConversionType, StreamSource, StreamSources
from ts2mp4.video_file import AudioStream, Stream, VideoFile, VideoStream


class _StreamSpec(NamedTuple):
    """Stream fields for one stream in disposition selection cases."""

    codec_type: str
    stream_index: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None


def _patch_probe(
    mocker: MockerFixture,
    path_to_output: dict[Path, FFprobeOutput],
) -> MagicMock:
    """Patch probe_file to return FFprobeOutput based on file path."""

    def _side_effect(path: Path) -> FFprobeOutput:
        return path_to_output[path]

    return mocker.patch("ts2mp4.video_file.probe_file", side_effect=_side_effect)


def _conversion_type_for_stream(stream: Stream) -> ConversionType:
    """Return a conversion_type suitable for StreamSource construction in tests."""
    if isinstance(stream, VideoStream):
        return "encoded"
    return "copied"


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
    mocker: MockerFixture,
    tmp_path: Path,
    stream_specs: tuple[_StreamSpec, ...],
    format_duration: float | None,
    expected: frozenset[int],
) -> None:
    """Select the primary video and audio stream indices for disposition default."""
    # Arrange
    source_path = tmp_path / "input.ts"
    source_path.touch()
    video_file = VideoFile(path=source_path)

    _patch_probe(
        mocker,
        {source_path: FFprobeOutput(format=FFprobeFormat(duration=format_duration))},
    )

    streams: list[Stream] = []
    for spec in stream_specs:
        if spec.codec_type == "video":
            streams.append(
                VideoStream(
                    file=video_file,
                    index=spec.stream_index,
                    width=spec.width,
                    height=spec.height,
                    duration=spec.duration,
                )
            )
        else:
            streams.append(
                AudioStream(
                    file=video_file, index=spec.stream_index, duration=spec.duration
                )
            )

    stream_sources = StreamSources(
        root=tuple(
            StreamSource(
                source_stream=stream,
                conversion_type=_conversion_type_for_stream(stream),
            )
            for stream in streams
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
    mocker: MockerFixture, tmp_path: Path
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
    file_a = VideoFile(path=path_a)
    file_b = VideoFile(path=path_b)

    low_res_video = VideoStream(
        file=file_a, index=0, width=720, height=480, duration=100.0
    )
    high_res_video = VideoStream(
        file=file_b, index=0, width=1440, height=1080, duration=100.0
    )
    audio = AudioStream(file=file_a, index=2, duration=100.0)

    mock_probe_file = _patch_probe(
        mocker,
        {
            path_a: FFprobeOutput(format=FFprobeFormat(duration=100.0)),
            path_b: FFprobeOutput(format=FFprobeFormat(duration=1000.0)),
        },
    )
    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=low_res_video,
                conversion_type="copied",
            ),
            StreamSource(
                source_stream=high_res_video,
                conversion_type="encoded",
            ),
            StreamSource(
                source_stream=audio,
                conversion_type="copied",
            ),
        )
    )

    # Act
    result = get_default_stream_indices(stream_sources)

    # Assert
    assert result == frozenset({0, 2})
    # Each stream consults its own source file (not a single shared container).
    probed_paths = [call.args[0] for call in mock_probe_file.call_args_list]
    assert path_a in probed_paths
    assert path_b in probed_paths
