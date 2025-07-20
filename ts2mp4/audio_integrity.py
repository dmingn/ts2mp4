from pathlib import Path

from logzero import logger

from .hashing import get_stream_md5
from .media_info import get_media_info


def _get_audio_stream_count(file_path: Path) -> int:
    """Returns the number of audio streams in a given file.

    Args:
        file_path: The path to the input file.

    Returns:
        The number of audio streams.
    """
    media_info = get_media_info(file_path)
    return sum(1 for stream in media_info.streams if stream.codec_type == "audio")


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
        get_stream_md5(input_file, "audio", i) for i in range(audio_stream_count)
    ]
    output_audio_md5s = [
        get_stream_md5(output_file, "audio", i) for i in range(audio_stream_count)
    ]

    if input_audio_md5s != output_audio_md5s:
        raise RuntimeError(
            f"Audio stream MD5 mismatch! Input: {input_audio_md5s}, Output: {output_audio_md5s}"
        )
    else:
        logger.info("Audio stream integrity verified successfully. MD5 hashes match.")
