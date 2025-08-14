"""A module for verifying stream integrity."""

from logzero import logger

from .hashing import get_stream_md5
from .media_info import Stream
from .video_file import ConversionType, ConvertedVideoFile, VideoFile


def compare_stream_hashes(
    input_video: VideoFile,
    output_video: VideoFile,
    input_stream: "Stream",
    output_stream: "Stream",
) -> bool:
    """Check the integrity of a single stream by comparing MD5 hashes.

    Returns
    -------
        True if the stream hashes match and hash generation is successful, False otherwise.
    """
    try:
        input_md5 = get_stream_md5(input_video.path, input_stream)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for input stream at index {input_stream.index}: {e}"
        )
        return False

    try:
        output_md5 = get_stream_md5(output_video.path, output_stream)
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


def verify_copied_streams(converted_file: ConvertedVideoFile) -> None:
    """Verify the integrity of copied streams by comparing their MD5 hashes.

    Args:
    ----
        converted_file: The ConvertedVideoFile object.

    Raises
    ------
        RuntimeError: If any copied stream's MD5 hash does not match.
    """
    logger.info(f"Verifying copied stream integrity for {converted_file.path.name}")

    for output_stream, stream_source in converted_file.stream_with_sources:
        if stream_source.conversion_type != ConversionType.COPIED:
            continue

        if not compare_stream_hashes(
            input_video=stream_source.source_video_file,
            output_video=converted_file,
            input_stream=stream_source.source_stream,
            output_stream=output_stream,
        ):
            stream_type = output_stream.codec_type or "Unknown"
            raise RuntimeError(
                f"{stream_type.capitalize()} stream integrity check "
                f"failed for stream at index {stream_source.source_stream.index}"
            )

    logger.info("Copied stream integrity verified successfully. All MD5 hashes match.")
