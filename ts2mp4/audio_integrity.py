from pathlib import Path

from logzero import logger

from .hashing import get_stream_md5
from .media_info import Stream, get_media_info


def check_stream_integrity(
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


def verify_audio_stream_integrity(input_file: Path, output_file: Path) -> None:
    """Verifies the integrity of audio streams by comparing their MD5 hashes.

    This function iterates through all audio streams in the input and output
    files, calculates their MD5 hashes, and compares them. If any pair of
    hashes does not match, or if an audio stream is present in one file but
    not the other, it raises a RuntimeError.

    Args:
    ----
        input_file: The path to the input file.
        output_file: The path to the output file.

    Raises:
    ------
        RuntimeError: If there's a mismatch in audio stream count, or if any
            audio stream's MD5 hash does not match between the input and
            output files.

    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )

    input_media_info = get_media_info(input_file)
    output_media_info = get_media_info(output_file)

    input_audio_streams = [
        s for s in input_media_info.streams if s.codec_type == "audio"
    ]
    output_audio_streams = [
        s for s in output_media_info.streams if s.codec_type == "audio"
    ]

    if len(input_audio_streams) != len(output_audio_streams):
        raise RuntimeError(
            "Mismatch in the number of audio streams: "
            f"{len(input_audio_streams)} in input, "
            f"{len(output_audio_streams)} in output."
        )

    for input_stream, output_stream in zip(input_audio_streams, output_audio_streams):
        if not check_stream_integrity(
            input_file, output_file, input_stream, output_stream
        ):
            raise RuntimeError(
                f"Audio stream integrity check failed for stream at index {input_stream.index}"
            )

    logger.info("Audio stream integrity verified successfully. All MD5 hashes match.")
