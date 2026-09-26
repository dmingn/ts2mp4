"""Encodes mismatched audio streams that failed integrity checks."""

from pathlib import Path
from typing import Self

from logzero import logger
from pydantic import model_validator

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .ffmpeg_args import build_ffmpeg_args
from .stream_integrity import IntegrityReport
from .stream_source import (
    AudioConversion,
    ConvertedVideoFile,
    Copy,
    EncodeAudio,
    StreamSource,
    StreamSources,
    streams_by_unique_index,
)
from .video_encoder import VideoEncodedFile
from .video_file import AudioStream, VideoFile, VideoStream

StreamSourceForAudioEncoding = (
    StreamSource[VideoStream, Copy] | StreamSource[AudioStream, AudioConversion]
)


class StreamSourcesForAudioEncoding(StreamSources):
    """Represents the stream sources for audio encoding."""

    root: tuple[StreamSourceForAudioEncoding, ...]

    @model_validator(mode="after")
    def validate_stream_presence(self) -> Self:
        """Validate the presence of at least one video and one audio stream."""
        if not self.video_stream_sources:
            raise ValueError("At least one video stream is required.")
        if not self.audio_stream_sources:
            raise ValueError("At least one audio stream is required.")
        return self

    @model_validator(mode="after")
    def validate_source_grouping(self) -> Self:
        """Validate the grouping and sources of the streams."""
        copied_sources = [s for s in self.root if isinstance(s.conversion, Copy)]
        sources_to_encode = [
            s for s in self.root if isinstance(s.conversion, EncodeAudio)
        ]

        if not copied_sources:
            raise ValueError("At least one stream must be copied.")

        encoded_files = {s.source_stream.file for s in copied_sources}
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


AudioEncodedFile = ConvertedVideoFile[StreamSourcesForAudioEncoding]
"""Represents a ConvertedVideoFile after mismatched audio encoding."""


def _build_stream_sources_for_audio_encoding(
    original_file: VideoFile,
    encoded_file: VideoEncodedFile,
    integrity_report: IntegrityReport,
) -> StreamSourcesForAudioEncoding:
    """Build the stream sources for audio encoding."""
    # Source streams are guaranteed to be unique for a video-encoded file.
    # stream_sources position i corresponds to output stream index i.
    streams_by_index = streams_by_unique_index(encoded_file.streams)
    original_encoded_stream_mapping = {
        stream_source.source_stream.index: streams_by_index[i]
        for i, stream_source in enumerate(encoded_file.stream_sources)
    }

    stream_sources_list: list[StreamSourceForAudioEncoding] = []

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
            stream_sources_list.append(
                StreamSource(
                    source_stream=matching_stream,
                    conversion=Copy(),
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
                stream_sources_list.append(
                    StreamSource(
                        source_stream=matching_stream,
                        conversion=Copy(),
                    )
                )
            else:
                # If the stream mismatches, it must be encoded from the original file
                stream_sources_list.append(
                    StreamSource(
                        source_stream=original_stream,
                        conversion=_build_encode_audio_for(original_stream),
                    )
                )

    return StreamSourcesForAudioEncoding(root=tuple(stream_sources_list))


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


def encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: VideoEncodedFile,
    integrity_report: IntegrityReport,
    output_file: Path,
) -> AudioEncodedFile:
    """Encode mismatched audio streams from an original file to a new output file.

    This function treats audio streams reported as mismatched in integrity_report
    as having different content compared to the original file. It then
    generates a new video file by:
    - Copying the video stream from the already encoded file.
    - Copying matching audio streams from the encoded file.
    - Encoding mismatched or missing audio streams from the original file.

    Args:
    ----
        original_file: The VideoFile object for the original source file (e.g., .ts).
        encoded_file: The VideoEncodedFile object from encode_video_streams.
                      It contains the mapping between original and encoded streams.
        integrity_report: The IntegrityReport from check_integrity on encoded_file.
                          It must report at least one mismatched stream.
        output_file: The path where the corrected output file will be saved.

    Returns
    -------
        The AudioEncodedFile written to output_file.

    Raises
    ------
        ValueError: If integrity_report reports no mismatched streams.
    """
    if integrity_report.is_ok:
        raise ValueError("integrity_report must report at least one mismatch.")

    stream_sources = _build_stream_sources_for_audio_encoding(
        original_file=original_file,
        encoded_file=encoded_file,
        integrity_report=integrity_report,
    )

    ffmpeg_args = build_ffmpeg_args(
        stream_sources=stream_sources,
        output_path=output_file,
    )

    execute_ffmpeg(ffmpeg_args)

    audio_encoded_file = AudioEncodedFile(
        path=output_file, stream_sources=stream_sources
    )

    return audio_encoded_file
