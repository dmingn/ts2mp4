import hashlib
import json
from pathlib import Path

from logzero import logger

from .ffmpeg import execute_ffmpeg, execute_ffprobe


def _get_audio_stream_count(file_path: Path) -> int:
    """Returns the number of audio streams in a given file.

    Args:
        file_path: The path to the input file.

    Returns:
        The number of audio streams.

    Raises:
        RuntimeError: If ffprobe fails to get stream information.
    """
    ffprobe_args = [
        "-hide_banner",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(file_path),
    ]
    result = execute_ffprobe(ffprobe_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed to get stream information for {file_path}. "
            f"Return code: {result.returncode}"
        )
    data = json.loads(result.stdout.decode("utf-8"))
    return sum(
        1 for stream in data.get("streams", []) if stream.get("codec_type") == "audio"
    )


def _get_audio_stream_md5(file_path: Path, stream_index: int) -> str:
    """Calculates the MD5 hash of the decoded audio stream of a given file.

    Args:
        file_path: The path to the input file.
        stream_index: The index of the audio stream to process.

    Returns:
        The MD5 hash of the decoded audio stream as a hexadecimal string.

    Raises:
        RuntimeError: If ffmpeg fails to extract the audio stream.
    """
    ffmpeg_args = [
        "-hide_banner",
        "-i",
        str(file_path),
        "-map",
        f"0:a:{stream_index}",
        "-vn",  # No video
        "-f",
        "s16le",  # Output raw signed 16-bit little-endian PCM
        "-",  # Output to stdout
    ]
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to get decoded audio stream for {file_path}. "
            f"Return code: {result.returncode}"
        )
    return hashlib.md5(result.stdout).hexdigest()


def verify_audio_stream_integrity(input_file: Path, output_file: Path) -> None:
    """Verifies the integrity of audio streams by comparing MD5 hashes before and after conversion.

    Args:
        input_file: The path to the original input file.
        output_file: The path to the converted output file.

    Raises:
        RuntimeError: If audio stream MD5 hashes do not match.
    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )
    audio_stream_count = _get_audio_stream_count(input_file)
    logger.info(f"Detected {audio_stream_count} audio streams in input file.")

    input_audio_md5s = [
        _get_audio_stream_md5(input_file, i) for i in range(audio_stream_count)
    ]
    output_audio_md5s = [
        _get_audio_stream_md5(output_file, i) for i in range(audio_stream_count)
    ]

    if input_audio_md5s != output_audio_md5s:
        raise RuntimeError(
            f"Audio stream MD5 mismatch! Input: {input_audio_md5s}, Output: {output_audio_md5s}"
        )
    else:
        logger.info("Audio stream integrity verified successfully. MD5 hashes match.")
