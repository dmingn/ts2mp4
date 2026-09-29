"""Builds the file conversion plan that re-encodes audio streams failing integrity checks."""

from typing import Self

from logzero import logger
from pydantic import model_validator

from .conversion_plan import (
    AudioConversionMethod,
    Copy,
    EncodeAudio,
    FileConversionPlan,
    StreamConversionPlan,
    streams_by_unique_index,
)
from .ffmpeg import is_libfdk_aac_available
from .stream_integrity import IntegrityReport
from .video_encoder import VideoEncodedFile
from .video_file import AudioStream, VideoFile, VideoStream

StreamConversionPlanForAudioEncoding = (
    StreamConversionPlan[VideoStream, Copy]
    | StreamConversionPlan[AudioStream, AudioConversionMethod]
)


class FileConversionPlanForAudioEncoding(FileConversionPlan):
    """Represents the file conversion plan for audio encoding."""

    root: tuple[StreamConversionPlanForAudioEncoding, ...]

    @model_validator(mode="after")
    def validate_stream_presence(self) -> Self:
        """Validate the presence of at least one video and one audio stream."""
        if not self.video_stream_plans:
            raise ValueError("At least one video stream is required.")
        if not self.audio_stream_plans:
            raise ValueError("At least one audio stream is required.")
        return self

    @model_validator(mode="after")
    def validate_source_grouping(self) -> Self:
        """Validate the grouping and sources of the streams."""
        copied_plans = [s for s in self.root if isinstance(s.conversion_method, Copy)]
        sources_to_encode = [
            s for s in self.root if isinstance(s.conversion_method, EncodeAudio)
        ]

        if not copied_plans:
            raise ValueError("At least one stream must be copied.")

        encoded_files = {s.source_stream.file for s in copied_plans}
        if len(encoded_files) != 1:
            raise ValueError("All copied streams must come from the same encoded file.")

        if sources_to_encode:
            original_files = {s.source_stream.file for s in sources_to_encode}
            if len(original_files) != 1:
                raise ValueError(
                    "All streams to encode must come from the same original file."
                )

            encoded_file = encoded_files.pop()
            original_file = original_files.pop()
            if original_file.path == encoded_file.path:
                raise ValueError(
                    "Original and encoded files cannot be the same when encoding audio."
                )

        return self


def build_file_conversion_plan_for_audio_encoding(
    original_file: VideoFile,
    encoded_file: VideoEncodedFile,
    integrity_report: IntegrityReport,
) -> FileConversionPlanForAudioEncoding:
    """Build the file conversion plan that fixes mismatched audio streams.

    Video streams and matching audio streams are copied from ``encoded_file``.
    Audio streams reported as mismatched in ``integrity_report`` are encoded
    from ``original_file`` with their original settings.

    Args:
    ----
        original_file: The VideoFile object for the original source file (e.g., .ts).
        encoded_file: The VideoEncodedFile produced from original_file.
                      It contains the mapping between original and encoded streams.
        integrity_report: The IntegrityReport from check_integrity on encoded_file.
                          It must report at least one mismatched stream.

    Raises
    ------
        ValueError: If integrity_report reports no mismatched streams.
    """
    if integrity_report.is_ok:
        raise ValueError("integrity_report must report at least one mismatch.")

    # Source streams are guaranteed to be unique for a video-encoded file.
    # file_conversion_plan position i corresponds to output stream index i.
    streams_by_index = streams_by_unique_index(encoded_file.streams)
    original_encoded_stream_mapping = {
        plan.source_stream.index: streams_by_index[i]
        for i, plan in enumerate(encoded_file.file_conversion_plan)
    }

    plans: list[StreamConversionPlanForAudioEncoding] = []

    for original_stream in sorted(original_file.valid_streams):
        matching_stream = original_encoded_stream_mapping.get(original_stream.index)

        if not matching_stream:
            raise RuntimeError(
                f"Encoded file {encoded_file.path.name} is missing a required stream "
                f"from the original {original_file.path.name}."
            )

        if isinstance(original_stream, VideoStream):
            if not isinstance(matching_stream, VideoStream):
                raise RuntimeError(
                    f"Mismatch in stream types for file {encoded_file.path.name}: "
                    f"Stream at index {matching_stream.index} was expected to be "
                    f"'video', but was '{type(matching_stream).__name__}'."
                )

            # Video streams should be always copied from the encoded file
            plans.append(
                StreamConversionPlan(
                    source_stream=matching_stream,
                    conversion_method=Copy(),
                )
            )
        elif isinstance(original_stream, AudioStream):
            if not isinstance(matching_stream, AudioStream):
                raise RuntimeError(
                    f"Mismatch in stream types for file {encoded_file.path.name}: "
                    f"Stream at index {matching_stream.index} was expected to be "
                    f"'audio', but was '{type(matching_stream).__name__}'."
                )

            if matching_stream.index not in integrity_report.mismatched_output_indices:
                # If the stream matches, it can be copied from the encoded file
                plans.append(
                    StreamConversionPlan(
                        source_stream=matching_stream,
                        conversion_method=Copy(),
                    )
                )
            else:
                # If the stream mismatches, it must be encoded from the original file
                plans.append(
                    StreamConversionPlan(
                        source_stream=original_stream,
                        conversion_method=_build_encode_audio_for(original_stream),
                    )
                )

    return FileConversionPlanForAudioEncoding(root=tuple(plans))


_FFMPEG_AAC_PROFILES = {"LC": "aac_low"}


def _build_encode_audio_for(stream: AudioStream) -> EncodeAudio:
    """Return an EncodeAudio that re-encodes ``stream`` with its own settings.

    The sample rate, channel count, profile and bit rate are taken from
    ``stream``. The encoder is libfdk_aac when available, otherwise aac.
    """
    if stream.codec_name != "aac":
        raise NotImplementedError(
            "Encoding is currently only supported for aac audio codec."
        )

    if is_libfdk_aac_available():
        codec = "libfdk_aac"
    else:
        logger.warning(
            "libfdk_aac is not available. Falling back to the default AAC encoder."
        )
        codec = "aac"

    return EncodeAudio(
        codec=codec,
        sample_rate=stream.sample_rate,
        channels=stream.channels,
        profile=(
            _FFMPEG_AAC_PROFILES.get(stream.profile, stream.profile)
            if stream.profile is not None
            else None
        ),
        bit_rate=stream.bit_rate,
    )
