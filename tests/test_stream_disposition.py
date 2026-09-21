"""Unit tests for stream disposition selection."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import (
    AudioStream,
    Format,
    MediaInfo,
    Stream,
    VideoStream,
)
from ts2mp4.stream_disposition import (
    build_disposition_args,
    get_default_stream_indices,
)
from ts2mp4.video_file import ConversionType, StreamSource, StreamSources


def _patch_media_info(
    mocker: MockerFixture,
    path_to_media_info: dict[Path, MediaInfo],
) -> None:
    """Patch get_media_info to return MediaInfo based on file path."""

    def _side_effect(path: Path) -> MediaInfo:
        return path_to_media_info[path]

    mocker.patch("ts2mp4.video_file.get_media_info", side_effect=_side_effect)


def _conversion_type_for_stream(stream: Stream) -> ConversionType:
    """Return a conversion_type suitable for StreamSource construction in tests."""
    if isinstance(stream, VideoStream):
        return "encoded"
    return "copied"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("streams", "format_", "expected"),
    [
        pytest.param(
            (
                VideoStream(
                    codec_type="video",
                    index=0,
                    width=720,
                    height=480,
                    duration=6.657,
                ),
                VideoStream(
                    codec_type="video",
                    index=1,
                    width=1440,
                    height=1080,
                    duration=2407.0,
                ),
                AudioStream(codec_type="audio", index=2, channels=2, duration=2400.0),
            ),
            Format(duration=2407.0),
            frozenset({1, 2}),
            id="prefers_longer_video_over_short_remnant",
        ),
        pytest.param(
            (
                VideoStream(
                    codec_type="video",
                    index=0,
                    width=720,
                    height=480,
                    duration=1807.0,
                ),
                VideoStream(
                    codec_type="video",
                    index=1,
                    width=1440,
                    height=1080,
                    duration=1808.0,
                ),
                AudioStream(codec_type="audio", index=2, channels=2, duration=1807.0),
            ),
            Format(duration=1808.0),
            frozenset({1, 2}),
            id="prefers_higher_resolution_when_both_span",
        ),
        pytest.param(
            (
                VideoStream(
                    codec_type="video",
                    index=0,
                    width=1440,
                    height=1080,
                    duration=2407.0,
                ),
                AudioStream(codec_type="audio", index=1, channels=2, duration=6.464),
                AudioStream(codec_type="audio", index=2, channels=2, duration=2400.0),
            ),
            Format(duration=2407.0),
            frozenset({0, 2}),
            id="prefers_longer_audio_over_short_remnant",
        ),
        pytest.param(
            (
                VideoStream(
                    codec_type="video",
                    index=0,
                    width=720,
                    height=480,
                    duration=None,
                ),
                VideoStream(
                    codec_type="video",
                    index=1,
                    width=1440,
                    height=1080,
                    duration=2400.0,
                ),
                AudioStream(codec_type="audio", index=2, channels=2, duration=None),
                AudioStream(codec_type="audio", index=3, channels=2, duration=2400.0),
            ),
            Format(duration=2407.0),
            frozenset({1, 3}),
            id="prefers_known_duration_over_missing",
        ),
        pytest.param(
            (
                VideoStream(codec_type="video", index=0),
                VideoStream(codec_type="video", index=1),
                AudioStream(codec_type="audio", index=2, channels=2),
                AudioStream(codec_type="audio", index=3, channels=2),
            ),
            Format(format_name="mpegts"),
            frozenset({0, 2}),
            id="falls_back_to_first_when_duration_missing",
        ),
    ],
)
def test_get_default_stream_indices(
    mocker: MockerFixture,
    tmp_path: Path,
    streams: tuple[Stream, ...],
    format_: Format,
    expected: frozenset[int],
) -> None:
    """Select the primary video and audio stream indices for disposition default."""
    # Arrange
    source_path = tmp_path / "input.ts"
    source_path.touch()
    _patch_media_info(
        mocker,
        {
            source_path: MediaInfo(streams=streams, format=format_),
        },
    )
    stream_sources = StreamSources(
        root=tuple(
            StreamSource(
                source_video_path=source_path,
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
    """Look up container duration from each source's own video file."""
    # Arrange
    # path_a: short container so a low-res video that fills it spans.
    # path_b: long container so a high-res video of the same stream length does not.
    # If every stream wrongly used one path's container, resolution would pick index 1.
    path_a = tmp_path / "a.mp4"
    path_b = tmp_path / "b.ts"
    path_a.touch()
    path_b.touch()
    low_res_video = VideoStream(
        codec_type="video",
        index=0,
        width=720,
        height=480,
        duration=100.0,
    )
    high_res_video = VideoStream(
        codec_type="video",
        index=1,
        width=1440,
        height=1080,
        duration=100.0,
    )
    audio = AudioStream(codec_type="audio", index=2, channels=2, duration=100.0)
    mock_get_media_info = mocker.patch(
        "ts2mp4.video_file.get_media_info",
        side_effect=lambda path: {
            path_a: MediaInfo(
                streams=(low_res_video, high_res_video, audio),
                format=Format(duration=100.0),
            ),
            path_b: MediaInfo(
                streams=(low_res_video, high_res_video, audio),
                format=Format(duration=1000.0),
            ),
        }[path],
    )
    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_video_path=path_a,
                source_stream=low_res_video,
                conversion_type="copied",
            ),
            StreamSource(
                source_video_path=path_b,
                source_stream=high_res_video,
                conversion_type="encoded",
            ),
            StreamSource(
                source_video_path=path_a,
                source_stream=audio,
                conversion_type="copied",
            ),
        )
    )

    # Act
    result = get_default_stream_indices(stream_sources)

    # Assert
    assert result == frozenset({0, 2})
    assert mock_get_media_info.call_args_list == [
        mocker.call(path_a),
        mocker.call(path_b),
        mocker.call(path_a),
    ]
