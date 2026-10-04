"""Builds the file conversion plan that re-encodes problematic audio streams."""

from typing import Self

from logzero import logger
from pydantic import model_validator

from .audio_channels import SURROUND_5_1_CHANNELS, SURROUND_5_1_LAYOUT
from .conversion_plan import (
    AudioConversionMethod,
    AudioRateControl,
    BitRate,
    Copy,
    EncodeAudio,
    FileConversionPlan,
    StreamConversionPlan,
    VbrMode,
)
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
    fixed_surround_source_indices: frozenset[int],
    libfdk_aac_available: bool,
) -> FileConversionPlanForAudioEncoding:
    """Build the file conversion plan that fixes problematic audio streams.

    Video streams and the other audio streams are copied from ``encoded_file``.
    Audio streams in ``fixed_surround_source_indices`` are encoded from
    ``original_file`` as fixed 5.1ch. Audio streams reported as mismatched in
    ``integrity_report`` are encoded from ``original_file`` with their
    original channel count.

    Args:
    ----
        original_file: The VideoFile object for the original source file (e.g., .ts).
        encoded_file: The VideoEncodedFile produced from original_file.
                      It contains the mapping between original and encoded streams.
        integrity_report: The IntegrityReport from check_integrity on encoded_file.
        fixed_surround_source_indices: The indices of the audio streams in
                      original_file to encode as fixed 5.1ch.
        libfdk_aac_available: Whether ffmpeg can encode with libfdk_aac.

    Raises
    ------
        ValueError: If no stream needs to be encoded.
    """
    if integrity_report.is_ok and not fixed_surround_source_indices:
        raise ValueError(
            "integrity_report must report at least one mismatch "
            "or fixed_surround_source_indices must not be empty."
        )

    # Source streams are guaranteed to be unique for a video-encoded file.
    original_encoded_stream_mapping = {
        stream_with_conversion_plan.conversion_plan.source_stream.index: (
            stream_with_conversion_plan.stream
        )
        for stream_with_conversion_plan in encoded_file.streams_with_conversion_plans
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

            if original_stream.index in fixed_surround_source_indices:
                plans.append(
                    StreamConversionPlan(
                        source_stream=original_stream,
                        conversion_method=_build_fixed_surround_encode_audio_for(
                            original_stream, libfdk_aac_available
                        ),
                    )
                )
            elif matching_stream.index in integrity_report.mismatched_output_indices:
                plans.append(
                    StreamConversionPlan(
                        source_stream=original_stream,
                        conversion_method=_build_encode_audio_for(
                            original_stream, libfdk_aac_available
                        ),
                    )
                )
            else:
                plans.append(
                    StreamConversionPlan(
                        source_stream=matching_stream,
                        conversion_method=Copy(),
                    )
                )

    return FileConversionPlanForAudioEncoding(root=tuple(plans))


_FFMPEG_AAC_PROFILES = {"LC": "aac_low"}

_FIXED_SURROUND_AUDIO_FILTER = f"aformat=channel_layouts={SURROUND_5_1_LAYOUT}"

# Re-encoding an already lossy stream at its own bit rate compounds the loss,
# so libfdk_aac uses its highest quality VBR mode instead.
_LIBFDK_AAC_HIGHEST_VBR_MODE = 5


def _build_fixed_surround_encode_audio_for(
    stream: AudioStream, libfdk_aac_available: bool
) -> EncodeAudio:
    """Return an EncodeAudio that re-encodes ``stream`` as fixed 5.1ch.

    Stereo frames are upmixed into the front left and right channels, leaving
    the other channels silent.
    """
    return _build_encode_audio(
        stream,
        libfdk_aac_available,
        channels=SURROUND_5_1_CHANNELS,
        audio_filter=_FIXED_SURROUND_AUDIO_FILTER,
    )


def _build_encode_audio_for(
    stream: AudioStream, libfdk_aac_available: bool
) -> EncodeAudio:
    """Return an EncodeAudio that re-encodes ``stream`` with its own channel count."""
    return _build_encode_audio(
        stream, libfdk_aac_available, channels=stream.channels, audio_filter=None
    )


def _build_encode_audio(
    stream: AudioStream,
    libfdk_aac_available: bool,
    channels: int | None,
    audio_filter: str | None,
) -> EncodeAudio:
    """Return an EncodeAudio that re-encodes ``stream`` into ``channels`` channels.

    The sample rate and profile are taken from ``stream``. With libfdk_aac the
    quality is set by its highest VBR mode. Otherwise the aac encoder is used
    with the bit rate of ``stream`` scaled to ``channels``.
    """
    if stream.codec_name != "aac":
        raise NotImplementedError(
            "Encoding is currently only supported for aac audio codec."
        )

    if libfdk_aac_available:
        codec = "libfdk_aac"
        rate_control: AudioRateControl | None = VbrMode(
            mode=_LIBFDK_AAC_HIGHEST_VBR_MODE
        )
    else:
        logger.warning(
            "libfdk_aac is not available. Falling back to the default AAC encoder."
        )
        codec = "aac"
        rate_control = _scaled_bit_rate(stream, channels)

    return EncodeAudio(
        codec=codec,
        sample_rate=stream.sample_rate,
        channels=channels,
        profile=(
            _FFMPEG_AAC_PROFILES.get(stream.profile, stream.profile)
            if stream.profile is not None
            else None
        ),
        rate_control=rate_control,
        audio_filter=audio_filter,
    )


def _scaled_bit_rate(stream: AudioStream, channels: int | None) -> BitRate | None:
    """Return the bit rate of ``stream`` scaled to ``channels`` channels.

    The bit rate is kept as is when either channel count is unknown, and None
    is returned when the bit rate of ``stream`` is unknown.
    """
    if stream.bit_rate is None:
        return None

    if not stream.channels or channels is None:
        return BitRate(bit_rate=stream.bit_rate)

    return BitRate(bit_rate=stream.bit_rate * channels // stream.channels)
