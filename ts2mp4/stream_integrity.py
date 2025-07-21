from pathlib import Path
from typing import Optional

from logzero import logger

from .hashing import get_stream_md5
from .media_info import Stream, get_media_info


def check_stream_integrity(
    input_file: Path,
    output_file: Path,
    input_stream: "Stream",
    output_stream: "Stream",
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


def verify_stream_integrity(
    input_file: Path,
    output_file: Path,
    stream_type: str,
    type_specific_stream_indices: Optional[list[int]] = None,
) -> None:
    """Verifies the integrity of specified streams by comparing their MD5 hashes.

    Args:
    ----
        input_file: The path to the input file.
        output_file: The path to the output file.
        stream_type: The type of stream to verify ('audio', 'video', etc.).
        type_specific_stream_indices: A list of specific stream indices to check.
                                     If None, all streams of the specified
                                     type are checked.

    Raises:
    ------
        RuntimeError: If there's a mismatch in stream counts or if any
            stream's MD5 hash does not match.
    """
    logger.info(
        f"Verifying {stream_type} stream integrity for {input_file.name} and {output_file.name}"
    )

    input_media_info = get_media_info(input_file)
    output_media_info = get_media_info(output_file)

    input_streams = [s for s in input_media_info.streams if s.codec_type == stream_type]
    output_streams = [
        s for s in output_media_info.streams if s.codec_type == stream_type
    ]

    if type_specific_stream_indices is not None:
        input_streams = [input_streams[i] for i in type_specific_stream_indices]
        output_streams = [output_streams[i] for i in type_specific_stream_indices]

    if len(input_streams) != len(output_streams):
        raise RuntimeError(
            f"Mismatch in the number of {stream_type} streams: "
            f"{len(input_streams)} in input, {len(output_streams)} in output."
        )

    for input_stream, output_stream in zip(input_streams, output_streams):
        if not check_stream_integrity(
            input_file, output_file, input_stream, output_stream
        ):
            raise RuntimeError(
                f"{stream_type.capitalize()} stream integrity check failed for stream at index "
                f"{input_stream.index}"
            )

    logger.info(
        f"{stream_type.capitalize()} stream integrity verified successfully. All MD5 hashes match."
    )
