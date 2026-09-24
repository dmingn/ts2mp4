"""Encodes mismatched audio streams that failed integrity checks."""

from pathlib import Path
from typing import Literal, Optional, Self

from logzero import logger
from pydantic import model_validator

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .stream_disposition import build_disposition_args
from .stream_integrity import compare_stream_hashes
from .stream_source import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    StreamSources,
    is_audio_stream_source,
    streams_by_unique_index,
)
from .video_encoder import VideoEncodedFile
from .video_file import AudioStream, VideoFile, VideoStream

StreamSourceForAudioEncoding = (
    StreamSource[VideoStream, Literal["copied"]]
    | StreamSource[AudioStream, Literal["copied", "encoded"]]
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
        copied_sources = [s for s in self.root if s.conversion_type == "copied"]
        sources_to_encode = [s for s in self.root if s.conversion_type == "encoded"]

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
    original_file: VideoFile, encoded_file: VideoEncodedFile
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
                    conversion_type="copied",
                )
            )
        elif isinstance(original_stream, AudioStream):
            if not isinstance(matching_stream, AudioStream):
                raise RuntimeError(
                    f"Mismatch in stream types for file {encoded_file.path.name}: "
                    f"Stream at index {matching_stream.index} was expected to be "
                    f"'audio', but was '{type(matching_stream).__name__}'."
                )

            if compare_stream_hashes(original_stream, matching_stream):
                # If the hashes match, the stream can be copied from the encoded file
                stream_sources_list.append(
                    StreamSource(
                        source_stream=matching_stream,
                        conversion_type="copied",
                    )
                )
            else:
                # If the hashes do not match, the stream must be encoded from the original file
                stream_sources_list.append(
                    StreamSource(
                        source_stream=original_stream,
                        conversion_type="encoded",
                    )
                )

    return StreamSourcesForAudioEncoding(root=tuple(stream_sources_list))


def _build_audio_encode_args(
    stream_source: StreamSource[AudioStream, ConversionType], output_stream_index: int
) -> list[str]:
    """Build FFmpeg arguments for encoding an audio stream."""
    original_audio_stream = stream_source.source_stream

    codec_name = str(original_audio_stream.codec_name)
    if original_audio_stream.codec_name == "aac":
        if is_libfdk_aac_available():
            codec_name = "libfdk_aac"
        else:
            logger.warning(
                "libfdk_aac is not available. Falling back to the default AAC encoder."
            )
    else:
        raise NotImplementedError(
            "Encoding is currently only supported for aac audio codec."
        )

    encode_args = [
        f"-codec:{output_stream_index}",
        codec_name,
    ]
    if original_audio_stream.sample_rate is not None:
        encode_args.extend(
            [
                f"-ar:{output_stream_index}",
                str(original_audio_stream.sample_rate),
            ]
        )
    if original_audio_stream.channels is not None:
        encode_args.extend(
            [
                f"-ac:{output_stream_index}",
                str(original_audio_stream.channels),
            ]
        )
    if original_audio_stream.profile is not None:
        profile_map = {"LC": "aac_low"}
        profile = profile_map.get(
            original_audio_stream.profile, original_audio_stream.profile
        )
        encode_args.extend(
            [
                f"-profile:{output_stream_index}",
                profile,
            ]
        )
    if original_audio_stream.bit_rate is not None:
        encode_args.extend(
            [
                f"-b:{output_stream_index}",
                str(original_audio_stream.bit_rate),
            ]
        )
    encode_args.extend([f"-bsf:{output_stream_index}", "aac_adtstoasc"])
    return encode_args


def _build_ffmpeg_args_from_stream_sources(
    stream_sources: StreamSourcesForAudioEncoding,
    output_path: Path,
) -> list[str]:
    """Build FFmpeg arguments from a StreamSources object."""
    # Create a unique, ordered list of input files and a mapping to their index
    input_files = list(dict.fromkeys(s.source_stream.file for s in stream_sources))
    input_file_map = {file: i for i, file in enumerate(input_files)}

    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
    ]

    # Add -i arguments for each unique input file
    for file in input_files:
        ffmpeg_args.extend(["-i", str(file.path)])

    # Add -map and codec arguments for each stream
    for i, source in enumerate(stream_sources):
        input_index = input_file_map[source.source_stream.file]

        # Add map argument using the original stream index from the source file
        ffmpeg_args.extend(["-map", f"{input_index}:{source.source_stream.index}"])

        # Add codec arguments using the global output stream index
        if source.conversion_type == "copied":
            ffmpeg_args.extend([f"-codec:{i}", "copy"])
        elif is_audio_stream_source(source):
            ffmpeg_args.extend(_build_audio_encode_args(source, i))
        else:
            # This path should be unreachable due to validation in StreamSourcesForAudioEncoding
            raise ValueError(
                f"Invalid conversion requested for stream type "
                f"'{type(source.source_stream).__name__}'."
            )

    ffmpeg_args.extend(build_disposition_args(stream_sources))

    # Add final output arguments
    ffmpeg_args.extend(["-f", "mp4", str(output_path)])

    return ffmpeg_args


def encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: VideoEncodedFile,
    output_file: Path,
) -> Optional[AudioEncodedFile]:
    """Encode mismatched audio streams from an original file to a new output file.

    This function identifies audio streams that are either missing in the encoded
    file or have different content compared to the original file. It then
    generates a new video file by:
    - Copying the video stream from the already encoded file.
    - Copying matching audio streams from the encoded file.
    - Encoding mismatched or missing audio streams from the original file.

    Args:
    ----
        original_file: The VideoFile object for the original source file (e.g., .ts).
        encoded_file: The VideoEncodedFile object from encode_video_streams.
                      It contains the mapping between original and encoded streams.
        output_file: The path where the corrected output file will be saved.

    Returns
    -------
        An AudioEncodedFile object if encoding was performed, otherwise None.
    """
    stream_sources = _build_stream_sources_for_audio_encoding(
        original_file=original_file, encoded_file=encoded_file
    )

    # If all audio streams are to be copied, no encoding is needed.
    if not any(s.conversion_type == "encoded" for s in stream_sources):
        logger.info("No audio streams require encoding. Skipping.")
        return None

    ffmpeg_args = _build_ffmpeg_args_from_stream_sources(
        stream_sources=stream_sources,
        output_path=output_file,
    )

    execute_ffmpeg(ffmpeg_args)

    audio_encoded_file = AudioEncodedFile(
        path=output_file, stream_sources=stream_sources
    )

    return audio_encoded_file
