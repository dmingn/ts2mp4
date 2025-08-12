"""Re-encodes audio streams that have integrity issues."""

import itertools
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple, Optional

from logzero import logger

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .quality_check import get_audio_quality_metrics
from .stream_integrity import compare_stream_hashes, verify_streams
from .video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


class ReEncodePlan(NamedTuple):
    """A tuple containing the stream sources and FFmpeg arguments for re-encoding."""

    stream_sources: Mapping[int, StreamSource]
    ffmpeg_args: list[str]


def _prepare_audio_re_encode_plan(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_path: Path,
) -> Optional[ReEncodePlan]:
    """Prepare a plan for re-encoding mismatched audio streams."""
    video_stream = next(iter(encoded_file.video_streams), None)
    if not video_stream:
        raise ValueError("Encoded file has no video streams.")

    new_stream_sources = {
        0: encoded_file.stream_sources[video_stream.index].model_copy(
            update={"conversion_type": ConversionType.COPIED}
        )
    }

    needs_re_encoding = False
    for i, (original_audio, encoded_audio) in enumerate(
        itertools.zip_longest(original_file.audio_streams, encoded_file.audio_streams)
    ):
        output_stream_index = len(new_stream_sources)

        if original_audio is None:
            raise RuntimeError("Encoded file has more audio streams than original.")

        integrity_check_passes = False
        if encoded_audio is not None:
            integrity_check_passes = compare_stream_hashes(
                original_file, encoded_file, original_audio, encoded_audio
            )

        if integrity_check_passes and encoded_audio is not None:
            new_stream_sources[output_stream_index] = encoded_file.stream_sources[
                encoded_audio.index
            ].model_copy(update={"conversion_type": ConversionType.COPIED})
        else:
            needs_re_encoding = True
            if original_audio.codec_name != "aac":
                raise NotImplementedError(
                    "Re-encoding is only supported for AAC audio."
                )

            new_stream_sources[output_stream_index] = StreamSource(
                source_video_file=original_file,
                source_stream_index=original_audio.index,
                conversion_type=ConversionType.RE_ENCODED,
            )

    if not needs_re_encoding:
        return None

    # Build FFmpeg arguments
    source_files = {s.source_video_file.path for s in new_stream_sources.values()}
    input_files = sorted(list(source_files))
    input_map = {path: i for i, path in enumerate(input_files)}

    map_args = []
    codec_args = []

    for stream_index, source in new_stream_sources.items():
        input_index = input_map[source.source_video_file.path]
        map_args.extend(["-map", f"{input_index}:{source.source_stream_index}"])

        if source.conversion_type == ConversionType.COPIED:
            codec_args.extend([f"-codec:{stream_index}", "copy"])
        elif source.conversion_type == ConversionType.RE_ENCODED:
            original_stream = source.source_video_file.get_stream_by_index(
                source.source_stream_index
            )
            codec_name = str(original_stream.codec_name)
            if original_stream.codec_name == "aac":
                if is_libfdk_aac_available():
                    codec_name = "libfdk_aac"
                else:
                    logger.warning(
                        "libfdk_aac not available, falling back to default AAC encoder."
                    )
            codec_args.extend([f"-codec:{stream_index}", codec_name])
            if original_stream.bit_rate:
                codec_args.extend([f"-b:{stream_index}", str(original_stream.bit_rate)])

    ffmpeg_args = (
        ["-hide_banner", "-nostats", "-y"]
        + [arg for path in input_files for arg in ("-i", str(path))]
        + map_args
        + codec_args
        + ["-f", "mp4", "-bsf:a", "aac_adtstoasc", str(output_path)]
    )

    return ReEncodePlan(
        stream_sources=MappingProxyType(new_stream_sources), ffmpeg_args=ffmpeg_args
    )


def re_encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_file: Path,
) -> Optional[ConvertedVideoFile]:
    """Re-encodes mismatched audio streams from an original file to a new output file."""
    plan = _prepare_audio_re_encode_plan(original_file, encoded_file, output_file)

    if not plan:
        logger.info("No audio streams require re-encoding.")
        return None

    ffmpeg_result = execute_ffmpeg(plan.ffmpeg_args)
    if ffmpeg_result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {ffmpeg_result.returncode}")

    re_encoded_video = ConvertedVideoFile(
        path=output_file, stream_sources=plan.stream_sources
    )

    copied_audio_indices = [
        i
        for i, s in re_encoded_video.stream_sources.items()
        if s.conversion_type == ConversionType.COPIED
        and s.source_video_file.get_stream_by_index(s.source_stream_index).codec_type
        == "audio"
    ]

    verify_streams(
        input_file=encoded_file, output_file=re_encoded_video, stream_type="video"
    )
    if copied_audio_indices:
        verify_streams(
            input_file=encoded_file,
            output_file=re_encoded_video,
            stream_type="audio",
            type_specific_stream_indices=copied_audio_indices,
        )

    for i, source in re_encoded_video.stream_sources.items():
        if source.conversion_type == ConversionType.RE_ENCODED:
            metrics = get_audio_quality_metrics(original_file.path, output_file, i)
            if metrics:
                log_parts = [
                    f"{k}={v:.2f}dB"
                    for k, v in metrics._asdict().items()
                    if v is not None
                ]
                if log_parts:
                    logger.info(f"Audio quality for stream {i}: {', '.join(log_parts)}")

    return re_encoded_video
