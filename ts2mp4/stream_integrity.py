"""A module for verifying stream integrity between video files."""

from typing import Literal, Optional

from logzero import logger

from .hashing import get_stream_md5
from .media_info import get_media_info
from .video_file import ConversionType, ConvertedVideoFile, VideoFile


class StreamIntegrityError(Exception):
    """Custom exception for stream integrity verification errors."""


def verify_streams(
    input_file: VideoFile,
    output_file: VideoFile,
    stream_type: Literal["video", "audio"],
    accepted_conversion_types: Optional[list[ConversionType]] = None,
) -> None:
    """Verify the integrity of streams of a specific type between two video files.

    If `input_file` is a `ConvertedVideoFile`, it uses the `stream_sources` mapping
    to find the corresponding stream in the `output_file` (which is assumed to be
    the source for this comparison). Otherwise, it compares streams based on their order.

    Args:
        input_file: The input video file, potentially with lineage information.
        output_file: The file to compare against (the "source of truth").
        stream_type: The type of stream to verify ("video" or "audio").
        accepted_conversion_types: If provided, only streams with a conversion type
                                   in this list will be verified.
    """
    logger.info(
        f"Verifying {stream_type} stream integrity for {input_file.path.name} and {output_file.path.name}"
    )

    input_media_info = get_media_info(input_file.path)
    output_media_info = get_media_info(output_file.path)

    if not isinstance(input_file, ConvertedVideoFile):
        # ... (simple comparison logic remains the same)
        input_streams_of_type = [
            s for s in input_media_info.streams if s.codec_type == stream_type
        ]
        output_streams_of_type = [
            s for s in output_media_info.streams if s.codec_type == stream_type
        ]

        if len(input_streams_of_type) != len(output_streams_of_type):
            raise StreamIntegrityError(
                f"Mismatch in number of {stream_type} streams. "
                f"Input has {len(input_streams_of_type)}, "
                f"output has {len(output_streams_of_type)}."
            )

        for s_in, s_out in zip(input_streams_of_type, output_streams_of_type):
            input_hash = get_stream_md5(input_file.path, s_in)
            output_hash = get_stream_md5(output_file.path, s_out)
            if input_hash != output_hash:
                raise StreamIntegrityError(
                    f"MD5 hash mismatch for {stream_type} stream "
                    f"(input: {s_in.index}, output: {s_out.index})."
                )
        logger.info(
            f"{stream_type.capitalize()} stream integrity verified successfully. All hashes match."
        )
        return

    streams_verified_count = 0
    for input_stream_index, source_info in input_file.stream_sources.items():
        input_stream = input_media_info.streams[input_stream_index]

        if input_stream.codec_type != stream_type:
            continue

        if (
            accepted_conversion_types
            and source_info.conversion_type not in accepted_conversion_types
        ):
            continue

        if source_info.source_video_file.path != output_file.path:
            continue

        output_stream_index = source_info.source_stream_index
        output_stream = output_media_info.streams[output_stream_index]

        input_hash = get_stream_md5(input_file.path, input_stream)
        output_hash = get_stream_md5(output_file.path, output_stream)

        if input_hash != output_hash:
            raise StreamIntegrityError(
                f"MD5 hash mismatch for {stream_type} stream "
                f"(input: {input_stream_index}, source: {output_stream_index}). "
                f"Input hash: {input_hash}, Source hash: {output_hash}"
            )

        streams_verified_count += 1

    if streams_verified_count == 0:
        logger.warning(
            f"No matching {stream_type} streams found for verification in "
            f"{input_file.path.name} originating from {output_file.path.name}."
        )
    else:
        logger.info(
            f"{stream_type.capitalize()} stream integrity verified successfully for "
            f"{streams_verified_count} stream(s). All hashes match."
        )
