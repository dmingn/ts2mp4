"""Unit tests for the ffmpeg_args module."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ts2mp4.ffmpeg_args import (
    _encode_audio_args,
    _encode_video_args,
    build_ffmpeg_args,
)
from ts2mp4.stream_source import (
    Copy,
    EncodeAudio,
    EncodeVideo,
    StreamSource,
    StreamSources,
)
from ts2mp4.video_file import AudioStream, VideoFile, VideoStream


@pytest.mark.unit
def test_build_ffmpeg_args_maps_each_source_to_an_output_stream(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """build_ffmpeg_args maps each source from its input file in output order."""
    # Arrange
    encoded_path = tmp_path / "encoded.mp4"
    encoded_path.touch()
    encoded_file = VideoFile(path=encoded_path)

    original_path = tmp_path / "original.ts"
    original_path.touch()
    original_file = VideoFile(path=original_path)

    stream_sources = StreamSources(
        root=(
            StreamSource(
                source_stream=VideoStream(file=encoded_file, index=0),
                conversion=Copy(),
            ),
            StreamSource(
                source_stream=AudioStream(file=original_file, index=2),
                conversion=EncodeAudio(codec="aac"),
            ),
        )
    )

    mocker.patch(
        "ts2mp4.ffmpeg_args.build_disposition_args",
        return_value=["-disposition:0", "default"],
    )

    output_path = Path("output.mp4")

    # Act
    args = build_ffmpeg_args(stream_sources, output_path)

    # Assert
    assert args == [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(encoded_path),
        "-i",
        str(original_path),
        "-map",
        "0:0",
        "-codec:0",
        "copy",
        "-map",
        "1:2",
        "-codec:1",
        "aac",
        "-disposition:0",
        "default",
        "-f",
        "mp4",
        str(output_path),
    ]


@pytest.mark.unit
def test_encode_audio_args_includes_all_set_options() -> None:
    """_encode_audio_args emits every set option for the output stream."""
    # Arrange
    conversion = EncodeAudio(
        codec="aac",
        sample_rate=48000,
        channels=2,
        profile="aac_low",
        bit_rate=192000,
    )

    # Act
    args = _encode_audio_args(conversion, 1)

    # Assert
    assert args == [
        "-codec:1",
        "aac",
        "-ar:1",
        "48000",
        "-ac:1",
        "2",
        "-profile:1",
        "aac_low",
        "-b:1",
        "192000",
    ]


@pytest.mark.unit
def test_encode_audio_args_omits_unset_options() -> None:
    """_encode_audio_args omits options that are None."""
    # Arrange
    conversion = EncodeAudio(codec="aac")

    # Act
    args = _encode_audio_args(conversion, 1)

    # Assert
    assert args == ["-codec:1", "aac"]


@pytest.mark.unit
def test_encode_video_args_includes_all_set_options() -> None:
    """_encode_video_args emits every set option for the output stream."""
    # Arrange
    conversion = EncodeVideo(
        codec="libx265",
        crf=23,
        preset="medium",
        video_filter="bwdif",
        fps_mode="cfr",
    )

    # Act
    args = _encode_video_args(conversion, 0)

    # Assert
    assert args == [
        "-codec:0",
        "libx265",
        "-crf:0",
        "23",
        "-preset:0",
        "medium",
        "-filter:0",
        "bwdif",
        "-fps_mode:0",
        "cfr",
    ]


@pytest.mark.unit
def test_encode_video_args_omits_unset_options() -> None:
    """_encode_video_args omits options that are None."""
    # Arrange
    conversion = EncodeVideo(codec="libx265", crf=23, preset="medium")

    # Act
    args = _encode_video_args(conversion, 0)

    # Assert
    assert args == ["-codec:0", "libx265", "-crf:0", "23", "-preset:0", "medium"]
