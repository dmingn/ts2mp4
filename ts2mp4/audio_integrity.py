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


def get_mismatched_audio_stream_indices(
    input_file: Path, output_file: Path
) -> list[int]:
    """
    Verifies audio stream integrity by comparing MD5 hashes, returning problematic indices.

    This function compares the MD5 hashes of audio streams between an input and output file.
    It identifies streams where the hashes do not match or where hash generation fails for
    either the input or output stream.

    Args:
        input_file: Path to the original input file.
        output_file: Path to the converted output file.

    Returns:
        A list of integer indices for audio streams that have mismatched or failed MD5 hashes.
        An empty list is returned if all audio streams are verified successfully.
    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )
    audio_stream_count = _get_audio_stream_count(input_file)
    logger.info(f"Detected {audio_stream_count} audio streams in input file.")

    mismatched_indices = []
    for i in range(audio_stream_count):
        try:
            input_md5 = get_stream_md5(input_file, "audio", i)
            output_md5 = get_stream_md5(output_file, "audio", i)

            if input_md5 != output_md5:
                logger.warning(
                    f"Mismatch in audio stream {i}: "
                    f"Input MD5: {input_md5}, Output MD5: {output_md5}"
                )
                mismatched_indices.append(i)
        except RuntimeError as e:
            logger.warning(f"Failed to get MD5 for audio stream {i}: {e}")
            mismatched_indices.append(i)

    if not mismatched_indices:
        logger.info(
            "Audio stream integrity verified successfully. All MD5 hashes match."
        )
    else:
        logger.error(
            f"Found {len(mismatched_indices)} mismatched audio streams at "
            f"indices: {mismatched_indices}"
        )

    return mismatched_indices
