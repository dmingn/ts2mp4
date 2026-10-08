"""Unit and integration tests for the audio_channels module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from tests.helpers import TS_TIME_BASE, StubVideoFile
from ts2mp4.audio_channels import (
    UnsupportedChannelLayoutError,
    _get_frame_channel_counts_cached,
    find_streams_requiring_fixed_surround,
    get_frame_channel_counts,
    requires_fixed_surround,
)
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.video_file import AudioStream, VideoFile


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _get_frame_channel_counts_cached.cache_clear()


def _ffprobe_result(stdout: bytes) -> MagicMock:
    mock_result = MagicMock()
    mock_result.stdout = stdout
    return mock_result


def _stub_video_file(tmp_path: Path, *streams: FFprobeStream) -> VideoFile:
    path = tmp_path / "input.ts"
    path.touch()
    return StubVideoFile(path=path, stub_probe=FFprobeOutput(streams=streams))


@pytest.mark.unit
@pytest.mark.parametrize(
    "declared, observed, expected",
    [
        pytest.param(2, frozenset({2}), False, id="stereo_only"),
        pytest.param(6, frozenset({6}), False, id="consistent_5_1"),
        pytest.param(2, frozenset({2, 6}), True, id="mixed_stereo_and_5_1"),
        pytest.param(2, frozenset({6}), True, id="5_1_declared_as_stereo"),
        pytest.param(2, frozenset({1, 2}), False, id="mixed_without_5_1"),
    ],
)
def test_requires_fixed_surround(
    declared: int, observed: frozenset[int], expected: bool
) -> None:
    """requires_fixed_surround is True only for 5.1ch that is not consistently 5.1ch."""
    # Act
    result = requires_fixed_surround(declared, observed)

    # Assert
    assert result is expected


@pytest.mark.unit
def test_requires_fixed_surround_raises_for_unsupported_channel_count() -> None:
    """requires_fixed_surround rejects 5.1ch mixed with a non-stereo channel count."""
    # Act & Assert
    with pytest.raises(UnsupportedChannelLayoutError, match=r"\[1\]"):
        requires_fixed_surround(2, frozenset({1, 6}))


@pytest.mark.unit
def test_get_frame_channel_counts_returns_set_of_ffprobe_output(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """get_frame_channel_counts collects the per-frame channel counts into a set."""
    # Arrange
    video_file = _stub_video_file(tmp_path)
    mocker.patch(
        "ts2mp4.audio_channels.execute_ffprobe",
        return_value=_ffprobe_result(b"2\n2\n6\n6\n2\n"),
    )

    # Act
    result = get_frame_channel_counts(AudioStream(file=video_file, index=1))

    # Assert
    assert result == frozenset({2, 6})


@pytest.mark.unit
def test_get_frame_channel_counts_reads_only_the_given_stream(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """get_frame_channel_counts asks ffprobe for the frames of the given stream index."""
    # Arrange
    video_file = _stub_video_file(tmp_path)
    mock_execute_ffprobe = mocker.patch(
        "ts2mp4.audio_channels.execute_ffprobe",
        return_value=_ffprobe_result(b"2\n"),
    )

    # Act
    get_frame_channel_counts(AudioStream(file=video_file, index=3))

    # Assert
    args = mock_execute_ffprobe.call_args.args[0]
    assert args[args.index("-select_streams") + 1] == "3"


@pytest.mark.unit
def test_find_streams_requiring_fixed_surround_returns_mixed_stream_indices(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """find_streams_requiring_fixed_surround returns only the streams that need it."""
    # Arrange
    video_file = _stub_video_file(
        tmp_path,
        FFprobeStream(time_base=TS_TIME_BASE, codec_type="video", index=0),
        FFprobeStream(time_base=TS_TIME_BASE, codec_type="audio", index=1, channels=2),
        FFprobeStream(time_base=TS_TIME_BASE, codec_type="audio", index=2, channels=2),
    )
    frame_channel_counts = {1: frozenset({2, 6}), 2: frozenset({2})}
    mocker.patch(
        "ts2mp4.audio_channels.get_frame_channel_counts",
        side_effect=lambda stream: frame_channel_counts[stream.index],
    )

    # Act
    result = find_streams_requiring_fixed_surround(video_file)

    # Assert
    assert result == frozenset({1})


@pytest.mark.unit
def test_find_streams_requiring_fixed_surround_notes_stream_on_unsupported_layout(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """find_streams_requiring_fixed_surround tells which stream has an unsupported layout."""
    # Arrange
    video_file = _stub_video_file(
        tmp_path,
        FFprobeStream(time_base=TS_TIME_BASE, codec_type="audio", index=1, channels=2),
    )
    mocker.patch(
        "ts2mp4.audio_channels.get_frame_channel_counts",
        return_value=frozenset({1, 6}),
    )

    # Act & Assert
    with pytest.raises(UnsupportedChannelLayoutError) as exc_info:
        find_streams_requiring_fixed_surround(video_file)

    assert "Audio stream at index 1" in "".join(exc_info.value.__notes__)


@pytest.mark.integration
def test_get_frame_channel_counts_reads_real_mixed_surround_file(
    mixed_surround_ts_file: Path,
) -> None:
    """get_frame_channel_counts finds both stereo and 5.1ch in the mixed fixture."""
    # Arrange
    stream = AudioStream(file=VideoFile(path=mixed_surround_ts_file), index=1)

    # Act
    result = get_frame_channel_counts(stream)

    # Assert
    assert result == frozenset({2, 6})


@pytest.mark.integration
def test_find_streams_requiring_fixed_surround_ignores_real_mono_file(
    ts_file: Path,
) -> None:
    """find_streams_requiring_fixed_surround finds nothing in the mono fixture."""
    # Act
    result = find_streams_requiring_fixed_surround(VideoFile(path=ts_file))

    # Assert
    assert result == frozenset()
