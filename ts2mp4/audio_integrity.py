import itertools
from pathlib import Path

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
        input_md5 = get_stream_md5(input_file, input_stream.index)
        output_md5 = get_stream_md5(output_file, output_stream.index)

        if input_md5 != output_md5:
            logger.warning(
                f"Mismatch in stream at index {input_stream.index}: "
                f"Input MD5: {input_md5}, Output MD5: {output_md5}"
            )
            return False
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for stream at index {input_stream.index}: {e}"
        )
        return False

    return True


def get_mismatched_audio_stream_indices(
    input_file: Path, output_file: Path
) -> list[int]:
    """
    Verifies audio stream integrity by comparing MD5 hashes, returning problematic stream indices.

    This function compares the MD5 hashes of audio streams between an input and output file.
    It identifies streams where the hashes do not match or where hash generation fails for
    either the input or output stream.

    Args:
        input_file: Path to the original input file.
        output_file: Path to the converted output file.

    Returns:
        A list of stream indices for audio streams that have mismatched or failed MD5 hashes.
        An empty list is returned if all audio streams are verified successfully.
    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )

    input_media_info = get_media_info(input_file)
    output_media_info = get_media_info(output_file)

    mismatched_indices = []
    for input_stream, output_stream in itertools.zip_longest(
        input_media_info.streams, output_media_info.streams
    ):
        if (
            input_stream is None
        ):  # Should not happen if input_media_info.streams is the primary source
            continue

        if input_stream.codec_type == "audio":
            stream_index = input_stream.index

            if output_stream is None:
                logger.warning(
                    f"Audio stream at index {stream_index} in input file has no corresponding stream in output file."
                )
                mismatched_indices.append(stream_index)
                continue

            if output_stream.codec_type != "audio":
                logger.warning(
                    f"Stream at index {stream_index} in output file is not an audio stream (found {output_stream.codec_type})."
                )
                mismatched_indices.append(stream_index)
                continue

            if not _check_stream_integrity(
                input_file, output_file, input_stream, output_stream
            ):
                mismatched_indices.append(stream_index)

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
