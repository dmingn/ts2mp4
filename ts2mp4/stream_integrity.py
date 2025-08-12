"""A module for verifying stream integrity."""

from typing import Optional

from logzero import logger

from .hashing import get_stream_md5
from .media_info import Stream
from .video_file import ConvertedVideoFile, VideoFile


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


def verify_streams(
    input_file: VideoFile,
    output_file: VideoFile,
    stream_type: str,
    type_specific_stream_indices: Optional[list[int]] = None,
) -> None:
    """Verify the integrity of specified streams by comparing their MD5 hashes.

    Args:
    ----
        input_file: The VideoFile object for the input file.
        output_file: The VideoFile object for the output file.
        stream_type: The type of stream to verify ('audio', 'video', etc.).
        type_specific_stream_indices: A list of specific stream indices to check.
                                     If None, all streams of the specified
                                     type are checked.

    Raises
    ------
        RuntimeError: If there's a mismatch in stream counts or if any
            stream's MD5 hash does not match.
    """
    logger.info(
        f"Verifying {stream_type} stream integrity for {input_file.path.name} and {output_file.path.name}"
    )

    output_streams_to_check = [
        s for s in output_file.media_info.streams if s.codec_type == stream_type
    ]
    if type_specific_stream_indices is not None:
        output_streams_to_check = [
            s
            for s in output_streams_to_check
            if s.index in type_specific_stream_indices
        ]

    if isinstance(output_file, ConvertedVideoFile):
        input_streams_to_check = [
            output_file.get_source_stream(s) for s in output_streams_to_check
        ]
    else:
        # Fallback for non-converted files, assumes 1-to-1 mapping
        input_streams_to_check = [
            s for s in input_file.media_info.streams if s.codec_type == stream_type
        ]
        if type_specific_stream_indices is not None:
            input_streams_to_check = [
                s
                for s in input_streams_to_check
                if s.index in type_specific_stream_indices
            ]

    if len(input_streams_to_check) != len(output_streams_to_check):
        raise RuntimeError(
            f"Mismatch in the number of {stream_type} streams to check: "
            f"{len(input_streams_to_check)} in input, {len(output_streams_to_check)} in output."
        )

    for input_stream, output_stream in zip(
        input_streams_to_check, output_streams_to_check
    ):
        if not compare_stream_hashes(
            input_video=input_file,
            output_video=output_file,
            input_stream=input_stream,
            output_stream=output_stream,
        ):
            raise RuntimeError(
                f"{stream_type.capitalize()} stream integrity check failed for stream at index "
                f"{input_stream.index}"
            )

    logger.info(
        f"{stream_type.capitalize()} stream integrity verified successfully. All MD5 hashes match."
    )
