import itertools
from pathlib import Path
from typing import Optional

from logzero import logger

from .hashing import get_stream_md5
from .media_info import Stream, get_media_info


def _check_stream_integrity(
    input_file: Path,
    output_file: Path,
    input_stream: Stream,
    output_stream: Stream,
) -> bool:
    """Checks the integrity of a single stream by comparing MD5 hashes.

    Returns:
        True if the stream hashes match and hash generation is successful, False otherwise.
    """
    try:
        input_md5 = get_stream_md5(input_file, input_stream)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for input stream at index {input_stream.index}: {e}"
        )
        return False

    try:
        output_md5 = get_stream_md5(output_file, output_stream)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for output stream at index {output_stream.index}: {e}"
        )
        return False

    if input_md5 != output_md5:
        logger.warning(
            f"Mismatch in stream at index {input_stream.index}: "
            f"Input MD5: {input_md5}, Output MD5: {output_md5}"
        )
        return False

    return True


def get_mismatched_audio_stream_indices(
    input_file: Path, output_file: Path
) -> list[tuple[Optional[int], Optional[int]]]:
    """
    Verifies audio stream integrity by comparing MD5 hashes, returning problematic stream index pairs.

    This function compares the MD5 hashes of audio streams between an input and output file.
    It identifies streams where the hashes do not match or where hash generation fails for
    either the input or output stream.
    It assumes that the order of audio streams in the input and output files corresponds.

    Args:
        input_file: Path to the original input file.
        output_file: Path to the converted output file.

    Returns:
        A list of tuples, where each tuple contains (input_stream_index, output_stream_index)
        for audio streams that have mismatched or failed MD5 hashes.
        If an input or output stream does not have a corresponding stream, its index will be None.
        An empty list is returned if all audio streams are verified successfully.
    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )

    input_media_info = get_media_info(input_file)
    output_media_info = get_media_info(output_file)

    mismatched_indices: list[tuple[Optional[int], Optional[int]]] = []
    input_audio_streams = (
        stream for stream in input_media_info.streams if stream.codec_type == "audio"
    )
    output_audio_streams = (
        stream for stream in output_media_info.streams if stream.codec_type == "audio"
    )
    for input_audio_stream, output_audio_stream in itertools.zip_longest(
        input_audio_streams, output_audio_streams
    ):
        input_idx = input_audio_stream.index if input_audio_stream else None
        output_idx = output_audio_stream.index if output_audio_stream else None

        if input_audio_stream is None:
            logger.warning(
                f"Audio stream at index {output_idx} in output file has no corresponding stream in input file."
            )
            mismatched_indices.append((None, output_idx))
            continue

        if output_audio_stream is None:
            logger.warning(
                f"Audio stream at index {input_idx} in input file has no corresponding stream in output file."
            )
            mismatched_indices.append((input_idx, None))
            continue

        if not _check_stream_integrity(
            input_file, output_file, input_audio_stream, output_audio_stream
        ):
            mismatched_indices.append((input_idx, output_idx))

    if not mismatched_indices:
        logger.info(
            "Audio stream integrity verified successfully. All MD5 hashes match."
        )
    else:
        logger.error(
            f"Found {len(mismatched_indices)} mismatched audio stream pairs: {mismatched_indices}"
        )

    return mismatched_indices
