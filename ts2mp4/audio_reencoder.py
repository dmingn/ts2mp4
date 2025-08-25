"""Re-encodes audio streams that have integrity issues."""

from pathlib import Path
from typing import Optional

from logzero import logger
from pydantic import model_validator
from typing_extensions import Self

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .initial_converter import InitiallyConvertedVideoFile
from .media_info import AudioStream, Stream
from .quality_check import check_audio_quality
from .stream_integrity import compare_stream_hashes, verify_copied_streams
from .video_file import (
    ConvertedStreamSource,
    ConvertedVideoFile,
    CopiedStreamSource,
    StreamSource,
    StreamSources,
    VideoFile,
    is_audio_stream_source,
)


class StreamSourcesForAudioReEncoding(StreamSources):
    """Represents the stream sources for the audio re-encoding."""

    @model_validator(mode="after")
    def validate_stream_types(self) -> Self:
        """Validate that only video and audio streams are present."""
        if len(self.root) != len(self.video_stream_sources) + len(
            self.audio_stream_sources
        ):
            raise ValueError("Only video and audio streams are supported.")
        return self

    @model_validator(mode="after")
    def validate_stream_presence(self) -> Self:
        """Validate the presence of at least one video and one audio stream."""
        if not self.video_stream_sources:
            raise ValueError("At least one video stream is required.")
        if not self.audio_stream_sources:
            raise ValueError("At least one audio stream is required.")
        return self

    @model_validator(mode="after")
    def validate_video_stream_properties(self) -> Self:
        """Validate that all video streams are copied."""
        if not all(s.conversion_type == "copied" for s in self.video_stream_sources):
            raise ValueError("All video streams must be copied.")
        return self

    @model_validator(mode="after")
    def validate_source_grouping(self) -> Self:
        """Validate the grouping and sources of the streams."""
        copied_sources = [s for s in self.root if s.conversion_type == "copied"]
        converted_sources = [s for s in self.root if s.conversion_type == "converted"]

        if not copied_sources:
            raise ValueError("At least one stream must be copied.")

        encoded_files = {VideoFile(path=s.source_video_path) for s in copied_sources}
        if len(encoded_files) != 1:
            raise ValueError("All copied streams must come from the same encoded file.")

        if converted_sources:
            if not all(
                s.source_stream.codec_type == "audio" for s in converted_sources
            ):
                raise ValueError("Only audio streams can be converted.")

            original_files = {
                VideoFile(path=s.source_video_path) for s in converted_sources
            }
            if len(original_files) != 1:
                raise ValueError(
                    "All converted streams must come from the same original file."
                )

            encoded_file = encoded_files.pop()
            original_file = original_files.pop()
            if original_file == encoded_file:
                raise ValueError(
                    "Original and encoded files cannot be the same when re-encoding."
                )

        return self


class AudioReEncodedVideoFile(ConvertedVideoFile):
    """Represents a ConvertedVideoFile that has undergone audio re-encoding."""

    stream_sources: StreamSourcesForAudioReEncoding


def _build_stream_sources_for_audio_re_encoding(
    original_file: VideoFile, encoded_file: InitiallyConvertedVideoFile
) -> StreamSourcesForAudioReEncoding:
    """Build the stream sources for audio re-encoding."""
    # Source streams are guaranteed to be unique for an initially converted video file
    original_encoded_stream_mapping = {
        stream_source.source_stream: encoded_file.media_info.streams[i]
        for i, stream_source in enumerate(encoded_file.stream_sources)
    }

    stream_sources_list: list[StreamSource[Stream]] = []

    for original_stream in sorted(original_file.valid_streams, key=lambda s: s.index):
        matching_stream = original_encoded_stream_mapping.get(original_stream)

        if not matching_stream:
            raise RuntimeError(
                f"Encoded file {encoded_file.path.name} is missing a required stream "
                f"from the original {original_file.path.name}."
            )

        if original_stream.codec_type == "video":
            # Video streams should be always copied from the encoded file
            stream_sources_list.append(
                CopiedStreamSource(
                    source_video_path=encoded_file.path,
                    source_stream=matching_stream,
                )
            )
        elif original_stream.codec_type == "audio":
            if compare_stream_hashes(
                input_video=original_file,
                output_video=encoded_file,
                input_stream=original_stream,
                output_stream=matching_stream,
            ):
                # If the hashes match, the stream can be copied from the encoded file
                stream_sources_list.append(
                    CopiedStreamSource(
                        source_video_path=encoded_file.path,
                        source_stream=matching_stream,
                    )
                )
            else:
                # If the hashes do not match, the stream must be re-encoded from the original file
                stream_sources_list.append(
                    ConvertedStreamSource(
                        source_video_path=original_file.path,
                        source_stream=original_stream,
                    )
                )

    return StreamSourcesForAudioReEncoding(root=tuple(stream_sources_list))


def _build_audio_convert_args(
    stream_source: StreamSource[AudioStream], output_stream_index: int
) -> list[str]:
    """Build FFmpeg arguments for converting an audio stream."""
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
            "Re-encoding is currently only supported for aac audio codec."
        )

    convert_args = [
        f"-codec:{output_stream_index}",
        codec_name,
    ]
    if original_audio_stream.sample_rate is not None:
        convert_args.extend(
            [
                f"-ar:{output_stream_index}",
                str(original_audio_stream.sample_rate),
            ]
        )
    if original_audio_stream.channels is not None:
        convert_args.extend(
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
        convert_args.extend(
            [
                f"-profile:{output_stream_index}",
                profile,
            ]
        )
    if original_audio_stream.bit_rate is not None:
        convert_args.extend(
            [
                f"-b:{output_stream_index}",
                str(original_audio_stream.bit_rate),
            ]
        )
    convert_args.extend([f"-bsf:{output_stream_index}", "aac_adtstoasc"])
    return convert_args


def _build_ffmpeg_args_from_stream_sources(
    stream_sources: StreamSourcesForAudioReEncoding,
    output_path: Path,
) -> list[str]:
    """Build FFmpeg arguments from a StreamSources object."""
    # Create a unique, ordered list of input files and a mapping to their index
    input_files = list(
        dict.fromkeys(VideoFile(path=s.source_video_path) for s in stream_sources)
    )
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
        input_index = input_file_map[VideoFile(path=source.source_video_path)]

        # Add map argument using the original stream index from the source file
        ffmpeg_args.extend(["-map", f"{input_index}:{source.source_stream.index}"])

        # Add codec arguments using the global output stream index
        if source.conversion_type == "copied":
            ffmpeg_args.extend([f"-codec:{i}", "copy"])
        elif source.conversion_type == "converted" and is_audio_stream_source(source):
            ffmpeg_args.extend(_build_audio_convert_args(source, i))
        else:
            # This path should be unreachable due to validation in StreamSourcesForAudioReEncoding
            raise ValueError(
                f"Invalid conversion requested for stream type '{source.source_stream.codec_type}'."
            )

    # Add final output arguments
    ffmpeg_args.extend(["-f", "mp4", str(output_path)])

    return ffmpeg_args


def re_encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: InitiallyConvertedVideoFile,
    output_file: Path,
) -> Optional[AudioReEncodedVideoFile]:
    """Re-encodes mismatched audio streams from an original file to a new output file.

    This function identifies audio streams that are either missing in the encoded
    file or have different content compared to the original file. It then
    generates a new video file by:
    - Copying the video stream from the already encoded file.
    - Copying matching audio streams from the encoded file.
    - Re-encoding mismatched or missing audio streams from the original file.

    Args:
    ----
        original_file: The VideoFile object for the original source file (e.g., .ts).
        encoded_file: The InitiallyConvertedVideoFile object, which is the result of the
                      initial conversion. It contains the mapping between original and
                      encoded streams.
        output_file: The path where the corrected output file will be saved.

    Returns
    -------
        An AudioReEncodedVideoFile object if re-encoding was performed, otherwise None.
    """
    stream_sources = _build_stream_sources_for_audio_re_encoding(
        original_file=original_file, encoded_file=encoded_file
    )

    # If all audio streams are to be copied, no re-encoding is needed.
    if not any(isinstance(s, ConvertedStreamSource) for s in stream_sources):
        logger.info("No audio streams require re-encoding. Skipping.")
        return None

    ffmpeg_args = _build_ffmpeg_args_from_stream_sources(
        stream_sources=stream_sources,
        output_path=output_file,
    )

    # Execute the FFmpeg command
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    re_encoded_video_file = AudioReEncodedVideoFile(
        path=output_file, stream_sources=stream_sources
    )

    # Verify integrity of copied streams
    verify_copied_streams(re_encoded_video_file)

    # Get quality metrics for re-encoded streams
    quality_metrics = check_audio_quality(re_encoded_video_file)
    for stream_index, metrics in quality_metrics.items():
        log_parts = []
        if metrics.apsnr is not None:
            log_parts.append(f"APSNR={metrics.apsnr:.2f}dB")
        if metrics.asdr is not None:
            log_parts.append(f"ASDR={metrics.asdr:.2f}dB")
        if log_parts:
            logger.info(
                f"Audio quality for stream {stream_index}: {', '.join(log_parts)}"
            )

    return re_encoded_video_file
