"""Re-encodes audio streams that have integrity issues."""

from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, Optional

from logzero import logger

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .quality_check import get_audio_quality_metrics
from .stream_integrity import StreamIntegrityError, verify_streams
from .video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


class ReEncodePlan(NamedTuple):
    """A tuple containing the stream sources and FFmpeg arguments for re-encoding."""

    stream_sources: MappingProxyType[int, StreamSource]
    ffmpeg_args: list[str]


def _prepare_audio_re_encode_plan(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_path: Path,
) -> ReEncodePlan:
    """Prepare a plan for re-encoding mismatched audio streams."""
    new_stream_sources: dict[int, StreamSource] = {}
    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-y",
        "-i",
        str(original_file.path),
        "-i",
        str(encoded_file.path),
    ]
    map_args: list[str] = []
    codec_args: list[str] = []
    output_stream_index = 0

    # Video streams are copied directly from the already encoded file.
    for stream in encoded_file.video_streams:
        map_args.extend(["-map", f"1:{stream.index}"])
        codec_args.extend([f"-codec:{output_stream_index}", "copy"])
        new_stream_sources[output_stream_index] = encoded_file.stream_sources[
            stream.index
        ].model_copy(update={"conversion_type": ConversionType.COPIED})
        output_stream_index += 1

    # Audio streams are re-mapped.
    for stream in original_file.audio_streams:
        encoded_stream_index: Optional[int] = None
        for k, v in encoded_file.stream_sources.items():
            if v.source_stream_index == stream.index:
                encoded_stream_index = k
                break

        should_re_encode = False
        if encoded_stream_index is not None:
            try:
                verify_streams(
                    encoded_file,
                    original_file,
                    "audio",
                    accepted_conversion_types=[ConversionType.COPIED],
                )
                should_re_encode = False
            except StreamIntegrityError:
                should_re_encode = True
        else:
            should_re_encode = True

        if should_re_encode:
            # Re-encode from original file (input 0)
            map_args.extend(["-map", f"0:{stream.index}"])
            new_stream_sources[output_stream_index] = StreamSource(
                source_video_file=original_file,
                source_stream_index=stream.index,
                conversion_type=ConversionType.RE_ENCODED,
            )
            codec_name = "aac"
            if is_libfdk_aac_available():
                codec_name = "libfdk_aac"
            else:
                logger.warning(
                    "libfdk_aac not available, falling back to default AAC encoder."
                )
            codec_args.extend([f"-codec:{output_stream_index}", codec_name])
            if stream.bit_rate:
                codec_args.extend([f"-b:{output_stream_index}", str(stream.bit_rate)])
        elif encoded_stream_index is not None:
            # Copy from encoded file (input 1)
            map_args.extend(["-map", f"1:{encoded_stream_index}"])
            new_stream_sources[output_stream_index] = encoded_file.stream_sources[
                encoded_stream_index
            ].model_copy(update={"conversion_type": ConversionType.COPIED})
            codec_args.extend([f"-codec:{output_stream_index}", "copy"])

        output_stream_index += 1

    ffmpeg_args.extend(map_args)
    ffmpeg_args.extend(codec_args)
    ffmpeg_args.extend(["-f", "mp4", "-bsf:a", "aac_adtstoasc", str(output_path)])

    return ReEncodePlan(
        stream_sources=MappingProxyType(new_stream_sources), ffmpeg_args=ffmpeg_args
    )


def re_encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_file: Path,
) -> ConvertedVideoFile:
    """Re-encodes mismatched audio streams from an original file to a new output file."""
    plan = _prepare_audio_re_encode_plan(original_file, encoded_file, output_file)

    ffmpeg_result = execute_ffmpeg(plan.ffmpeg_args)
    if ffmpeg_result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {ffmpeg_result.returncode}")

    result = ConvertedVideoFile(path=output_file, stream_sources=plan.stream_sources)

    # Verify integrity of the new file
    verify_streams(
        input_file=result,
        output_file=encoded_file,
        stream_type="video",
        accepted_conversion_types=[ConversionType.COPIED],
    )
    verify_streams(
        input_file=result,
        output_file=original_file,
        stream_type="audio",
        accepted_conversion_types=[ConversionType.COPIED],
    )

    # Log quality metrics for re-encoded streams
    for i, source in result.stream_sources.items():
        if source.conversion_type == ConversionType.RE_ENCODED:
            metrics = get_audio_quality_metrics(
                source.source_video_file.path, output_file, i
            )
            if metrics:
                log_parts = [
                    f"{k}={v:.2f}dB"
                    for k, v in metrics._asdict().items()
                    if v is not None
                ]
                if log_parts:
                    logger.info(f"Audio quality for stream {i}: {', '.join(log_parts)}")

    return result
