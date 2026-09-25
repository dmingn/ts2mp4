"""A module for verifying stream integrity."""

from logzero import logger
from pydantic import BaseModel, ConfigDict

from .hashing import get_stream_md5
from .stream_source import ConvertedVideoFile, StreamSources, StreamWithSource
from .video_file import AudioStream, Stream, VideoStream


class IntegrityReport(BaseModel):
    """The result of comparing copied output streams against their sources."""

    mismatched_output_indices: frozenset[int]

    model_config = ConfigDict(frozen=True)

    @property
    def is_ok(self) -> bool:
        """Return True if every copied stream matches its source."""
        return not self.mismatched_output_indices


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


def _stream_matches_source(stream_with_source: StreamWithSource[Stream]) -> bool:
    """Return True if an output stream matches its source stream."""
    stream = stream_with_source.stream
    source_stream = stream_with_source.source.source_stream

    if not isinstance(stream, (AudioStream, VideoStream)) or not isinstance(
        source_stream, (AudioStream, VideoStream)
    ):
        raise NotImplementedError(
            "Stream integrity check for non-audio/video streams is not implemented."
        )

    return compare_stream_hashes(source_stream, stream)


def check_integrity(
    converted_file: ConvertedVideoFile[StreamSources],
) -> IntegrityReport:
    """Compare every copied stream in a converted file against its source.

    Args:
    ----
        converted_file: The ConvertedVideoFile object.

    Returns
    -------
        An IntegrityReport listing the output indices of mismatched streams.
    """
    return IntegrityReport(
        mismatched_output_indices=frozenset(
            stream_with_source.stream.index
            for stream_with_source in converted_file.stream_with_sources
            if stream_with_source.source.conversion_type == "copied"
            and not _stream_matches_source(stream_with_source)
        )
    )
