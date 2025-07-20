import json
from pathlib import Path

from logzero import logger

from .audio_integrity import _get_audio_stream_count
from .ffmpeg import execute_ffmpeg, execute_ffprobe


def _get_audio_stream_codec(file_path: Path, stream_index: int) -> str:
    """Returns the codec name of a specific audio stream.

    Args:
        file_path: The path to the input file.
        stream_index: The index of the audio stream.

    Returns:
        The codec name of the audio stream.

    Raises:
        RuntimeError: If ffprobe fails to get stream information.
    """
    ffprobe_args = [
        "-v",
        "error",
        "-select_streams",
        f"a:{stream_index}",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "json",
        str(file_path),
    ]
    result = execute_ffprobe(ffprobe_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed to get codec for {file_path} stream a:{stream_index}. "
            f"Return code: {result.returncode}"
        )
    data = json.loads(result.stdout.decode("utf-8"))
    return str(data["streams"][0]["codec_name"])


def _build_ffmpeg_args(
    original_ts_file: Path,
    output_mp4_file: Path,
    failed_stream_indices: list[int],
    temp_output_file: Path,
) -> list[str]:
    """Builds the ffmpeg command arguments for re-encoding and replacing streams."""
    ffmpeg_args = [
        "-y",
        "-i",
        str(output_mp4_file),
        "-i",
        str(original_ts_file),
        "-map",
        "0:v:0",
        "-map",
        "0:s?",
    ]

    # Stream mapping
    map_args = []
    codec_args = []

    # Audio streams
    audio_stream_count = _get_audio_stream_count(original_ts_file)

    audio_output_index = 0
    for i in range(audio_stream_count):
        if i in failed_stream_indices:
            # Re-encode from original TS file
            codec = _get_audio_stream_codec(original_ts_file, i)
            map_args.extend(["-map", f"1:a:{i}"])
            codec_args.extend(["-c:a", codec])
        else:
            # Copy from existing MP4 file
            map_args.extend(["-map", f"0:a:{i}"])
            codec_args.extend(["-c:a", "copy"])
        audio_output_index += 1

    ffmpeg_args.extend(map_args)
    ffmpeg_args.extend(codec_args)

    ffmpeg_args.extend(
        [
            "-codec:v",
            "copy",
            "-codec:s",
            "copy",
            str(temp_output_file),
        ]
    )
    return ffmpeg_args


def reencode_and_replace_audio_streams(
    original_ts_file: Path,
    output_mp4_file: Path,
    failed_stream_indices: list[int],
) -> None:
    """Re-encodes and replaces specified audio streams in an MP4 file.

    Args:
        original_ts_file: Path to the original TS file.
        output_mp4_file: Path to the output MP4 file to be repaired.
        failed_stream_indices: List of audio stream indices to re-encode and replace.
    """
    if not failed_stream_indices:
        logger.info("No failed audio streams to re-encode.")
        return

    logger.info(
        f"Re-encoding and replacing failed audio streams: {failed_stream_indices}"
    )

    temp_output_file = output_mp4_file.with_suffix(".temp.mp4")
    ffmpeg_args = _build_ffmpeg_args(
        original_ts_file,
        output_mp4_file,
        failed_stream_indices,
        temp_output_file,
    )

    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to re-encode and replace audio streams. "
            f"Return code: {result.returncode}"
        )

    output_mp4_file.unlink()
    temp_output_file.rename(output_mp4_file)
    logger.info("Successfully re-encoded and replaced failed audio streams.")
