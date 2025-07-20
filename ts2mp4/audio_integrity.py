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
        "-vn",
        "-f",
        "s16le",
        "-",
    ]
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to get decoded audio stream for {file_path}. "
            f"Return code: {result.returncode}"
        )
    return hashlib.md5(result.stdout).hexdigest()


def get_failed_audio_stream_indices_by_integrity_check(
    input_file: Path, output_file: Path
) -> list[int]:
    """
    Verifies the integrity of audio streams by comparing MD5 hashes and returns a list of failed stream indices.

    This function compares the MD5 hash of each audio stream in the input file with the corresponding stream
    in the output file. A stream is considered to have failed the integrity check if the MD5 hashes do not
    match, or if the MD5 hash could not be generated for either the input or output stream.

    Args:
        input_file: The path to the original input file (e.g., TS file).
        output_file: The path to the converted output file (e.g., MP4 file).

    Returns:
        A list of integer indices for the audio streams that failed the integrity check.
        An empty list is returned if all audio streams are verified successfully.
    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )
    audio_stream_count = _get_audio_stream_count(input_file)
    logger.info(f"Detected {audio_stream_count} audio streams in input file.")

    failed_stream_indices = []
    for i in range(audio_stream_count):
        logger.info(f"Verifying audio stream {i}...")
        try:
            input_md5 = _get_audio_stream_md5(input_file, i)
            output_md5 = _get_audio_stream_md5(output_file, i)
        except RuntimeError as e:
            logger.warning(f"MD5 hash generation failed for stream {i}: {e}")
            failed_stream_indices.append(i)
            continue

        if input_md5 != output_md5:
            logger.warning(
                f"MD5 mismatch for stream {i}. Input: {input_md5}, Output: {output_md5}. "
                "Adding to re-encode list."
            )
            failed_stream_indices.append(i)
        else:
            logger.info(f"Stream {i} MD5 hash matches: {input_md5}")

    if not failed_stream_indices:
        logger.info(
            "Audio stream integrity verified successfully. All MD5 hashes match."
        )
    else:
        logger.warning(
            f"Audio stream integrity check failed for streams: {failed_stream_indices}"
        )

    return failed_stream_indices
