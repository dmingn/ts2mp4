"""A module for verifying stream integrity."""

from logzero import logger

from .hashing import get_stream_md5
from .stream_source import ConvertedVideoFile, StreamSources
from .video_file import AudioStream, VideoStream


def compare_stream_hashes(
    stream_a: VideoStream | AudioStream,
    stream_b: VideoStream | AudioStream,
) -> bool:
    """Check the integrity of two streams by comparing MD5 hashes.

    Returns
    -------
        True if the stream hashes match and hash generation is successful,
        False otherwise.
    """
    try:
        md5_a = get_stream_md5(stream_a)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for stream at index {stream_a.index} "
            f"in {stream_a.file.path}: {e}"
        )
        return False

    try:
        md5_b = get_stream_md5(stream_b)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for stream at index {stream_b.index} "
            f"in {stream_b.file.path}: {e}"
        )
        return False

    if md5_a != md5_b:
        logger.warning(
            f"Mismatch in stream at index {stream_a.index}: "
            f"MD5 A: {md5_a}, MD5 B: {md5_b}"
        )
        return False

    return True


def verify_copied_streams(converted_file: ConvertedVideoFile[StreamSources]) -> None:
    """Verify the integrity of copied streams by comparing their MD5 hashes.

    Args:
    ----
        converted_file: The ConvertedVideoFile object.

    Raises
    ------
        RuntimeError: If any copied stream's MD5 hash does not match.
    """
    logger.info(f"Verifying copied stream integrity for {converted_file.path.name}")

    for stream_with_source in converted_file.stream_with_sources:
        if stream_with_source.source.conversion_type != "copied":
            continue

        if not isinstance(
            stream_with_source.stream, (AudioStream, VideoStream)
        ) or not isinstance(
            stream_with_source.source.source_stream, (AudioStream, VideoStream)
        ):
            raise NotImplementedError(
                "Stream integrity check for non-audio/video streams is not implemented."
            )

        if not compare_stream_hashes(
            stream_with_source.source.source_stream,
            stream_with_source.stream,
        ):
            stream_type = stream_with_source.stream.codec_type
            raise RuntimeError(
                f"{stream_type.capitalize()} stream integrity check "
                f"failed for stream at index "
                f"{stream_with_source.source.source_stream.index}"
            )

    logger.info("Copied stream integrity verified successfully. All MD5 hashes match.")
