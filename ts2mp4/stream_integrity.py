"""A module for verifying stream integrity."""

from typing import TypeVar

from logzero import logger
from pydantic import BaseModel, ConfigDict

from .conversion_plan import Copy, FileConversionPlan
from .converted_video_file import ConvertedVideoFile, StreamWithConversionPlan
from .ffmpeg import FFmpegRunner
from .hashing import get_stream_md5
from .video_file import AudioStream, OtherStream, Stream, VideoStream

DecodableStreamT = TypeVar("DecodableStreamT", VideoStream, AudioStream)


class IntegrityReport(BaseModel):
    """The result of comparing copied output streams against their sources."""

    mismatched_output_indices: frozenset[int]

    model_config = ConfigDict(frozen=True)

    @property
    def is_ok(self) -> bool:
        """Return True if every copied stream matches its source."""
        return not self.mismatched_output_indices


def compare_stream_hashes(
    stream_a: DecodableStreamT,
    stream_b: DecodableStreamT,
    ffmpeg_runner: FFmpegRunner,
) -> bool:
    """Check the integrity of two streams by comparing MD5 hashes.

    Returns
    -------
        True if the stream hashes match and hash generation is successful,
        False otherwise.
    """
    try:
        md5_a = get_stream_md5(stream_a, ffmpeg_runner)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for stream at index {stream_a.index} "
            f"in {stream_a.file.path}: {e}"
        )
        return False

    try:
        md5_b = get_stream_md5(stream_b, ffmpeg_runner)
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


def _audio_parameters(
    stream: AudioStream,
) -> tuple[str | None, str | None, int | None, int | None]:
    """Return the codec parameters of ``stream`` that a player decodes with."""
    return (stream.codec_name, stream.profile, stream.sample_rate, stream.channels)


def compare_audio_parameters(stream_a: AudioStream, stream_b: AudioStream) -> bool:
    """Check that two audio streams declare the same codec parameters.

    FFmpeg decodes an AAC stream copied into a container with its ADTS headers left in
    place, so the MD5 hashes still match, but other players cannot decode it
    because its decoder configuration is missing or wrong. This shows up as a
    different profile, sample rate or channel count.

    Returns
    -------
        True if the codec parameters match, False otherwise.
    """
    parameters_a = _audio_parameters(stream_a)
    parameters_b = _audio_parameters(stream_b)

    if parameters_a != parameters_b:
        logger.warning(
            f"Mismatch in audio parameters of stream at index {stream_a.index}: "
            "(codec, profile, sample rate, channels) "
            f"A: {parameters_a}, B: {parameters_b}"
        )
        return False

    return True


def _stream_matches_source(
    stream_with_conversion_plan: StreamWithConversionPlan[Stream],
    ffmpeg_runner: FFmpegRunner,
) -> bool:
    """Return True if an output stream matches its source stream."""
    stream = stream_with_conversion_plan.stream
    source_stream = stream_with_conversion_plan.conversion_plan.source_stream

    match (source_stream, stream):
        case (AudioStream(), AudioStream()):
            return compare_audio_parameters(
                source_stream, stream
            ) and compare_stream_hashes(source_stream, stream, ffmpeg_runner)
        case (VideoStream(), VideoStream()):
            return compare_stream_hashes(source_stream, stream, ffmpeg_runner)
        case (OtherStream(), _) | (_, OtherStream()):
            raise NotImplementedError(
                "Stream integrity check for non-audio/video streams is not implemented."
            )
        case _:
            raise ValueError(
                f"Stream type mismatch for stream index {stream.index} "
                f"in {stream.file.path.name}."
            )


def check_integrity(
    converted_file: ConvertedVideoFile[FileConversionPlan],
    ffmpeg_runner: FFmpegRunner,
) -> IntegrityReport:
    """Compare every copied stream in a converted file against its source.

    Args:
    ----
        converted_file: The ConvertedVideoFile object.
        ffmpeg_runner: The FFmpegRunner used to hash the streams.

    Returns
    -------
        An IntegrityReport listing the output indices of mismatched streams.
    """
    return IntegrityReport(
        mismatched_output_indices=frozenset(
            stream_with_conversion_plan.stream.index
            for stream_with_conversion_plan in converted_file.streams_with_conversion_plans
            if isinstance(
                stream_with_conversion_plan.conversion_plan.conversion_method, Copy
            )
            and not _stream_matches_source(stream_with_conversion_plan, ffmpeg_runner)
        )
    )
