"""A module for verifying stream integrity."""

from logzero import logger

from .hashing import get_stream_md5
from .video_file import ConversionType, ConvertedVideoFile


class StreamIntegrityError(Exception):
    """Custom exception for stream integrity verification errors."""


def verify_streams(converted_file: ConvertedVideoFile) -> None:
    """Verify the integrity of copied streams by comparing their MD5 hashes.

    This function iterates through the streams of a ConvertedVideoFile and,
    for any stream marked as COPIED, it compares its MD5 hash with the
    hash of its source stream to ensure they are identical.

    Args:
        converted_file: The converted video file to verify.

    Raises
    ------
        StreamIntegrityError: If any copied stream's MD5 hash does not
                              match its source.
    """
    logger.info(f"Verifying integrity of copied streams in {converted_file.path.name}")
    streams_checked = 0
    for dest_index, source in converted_file.stream_sources.items():
        if source.conversion_type != ConversionType.COPIED:
            continue

        streams_checked += 1
        source_file = source.source_video_file
        source_stream = source_file.media_info.streams[source.source_stream_index]
        dest_stream = converted_file.media_info.streams[dest_index]

        logger.debug(
            f"Verifying copied stream {dest_index} from "
            f"{source_file.path.name}:{source_stream.index}"
        )

        source_hash = get_stream_md5(source_file.path, source_stream)
        dest_hash = get_stream_md5(converted_file.path, dest_stream)

        if source_hash != dest_hash:
            raise StreamIntegrityError(
                f"MD5 hash mismatch for copied stream {dest_index}. "
                f"Source: {source_file.path.name}:{source_stream.index} ({source_hash}), "
                f"Destination: {converted_file.path.name}:{dest_index} ({dest_hash})"
            )

    if streams_checked > 0:
        logger.info(
            f"Successfully verified integrity of {streams_checked} copied stream(s)."
        )
    else:
        logger.info("No copied streams found to verify.")
