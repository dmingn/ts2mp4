"""Re-encodes audio streams that have integrity issues."""

from pathlib import Path
from typing import Optional

from logzero import logger

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .hashing import get_stream_md5
from .quality_check import get_audio_quality_metrics
from .video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)


def re_encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_file: Path,
) -> ConvertedVideoFile:
    """Re-encodes mismatched audio streams from an original file to a new output file."""
    new_stream_sources: dict[int, StreamSource] = {}
    ffmpeg_args: list[str] = [
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

    # --- Video Streams ---
    # Video streams are copied directly from the already encoded file.
    for stream in encoded_file.video_streams:
        map_args.extend(["-map", f"1:{stream.index}"])
        codec_args.extend([f"-codec:{output_stream_index}", "copy"])
        new_stream_sources[output_stream_index] = encoded_file.stream_sources[
            stream.index
        ].model_copy(update={"conversion_type": ConversionType.COPIED})
        output_stream_index += 1

    # --- Audio Streams ---
    # For each audio stream in the original file, decide whether to copy or re-encode.
    for original_audio_stream in original_file.audio_streams:
        # Find the corresponding stream in the encoded file via stream_sources
        encoded_audio_stream = None
        encoded_stream_index: Optional[int] = None
        for k, v in encoded_file.stream_sources.items():
            if v.source_stream_index == original_audio_stream.index:
                encoded_stream_index = k
                encoded_audio_stream = encoded_file.media_info.streams[k]
                break

        should_re_encode = False
        if encoded_audio_stream is not None and encoded_stream_index is not None:
            source_hash = get_stream_md5(original_file.path, original_audio_stream)
            dest_hash = get_stream_md5(encoded_file.path, encoded_audio_stream)
            if source_hash != dest_hash:
                should_re_encode = True
        else:
            should_re_encode = True

        if should_re_encode:
            logger.warning(
                f"Re-encoding audio stream {original_audio_stream.index} from {original_file.path.name}."
            )
            map_args.extend(["-map", f"0:{original_audio_stream.index}"])
            new_stream_sources[output_stream_index] = StreamSource(
                source_video_file=original_file,
                source_stream_index=original_audio_stream.index,
                conversion_type=ConversionType.RE_ENCODED,
            )
            codec_name = "aac"
            if is_libfdk_aac_available():
                codec_name = "libfdk_aac"
            codec_args.extend([f"-codec:{output_stream_index}", codec_name])
            if original_audio_stream.bit_rate:
                codec_args.extend(
                    [f"-b:{output_stream_index}", str(original_audio_stream.bit_rate)]
                )
        elif encoded_stream_index is not None:
            logger.debug(
                f"Copying matching audio stream {original_audio_stream.index} from {encoded_file.path.name}."
            )
            map_args.extend(["-map", f"1:{encoded_stream_index}"])
            new_stream_sources[output_stream_index] = encoded_file.stream_sources[
                encoded_stream_index
            ].model_copy(update={"conversion_type": ConversionType.COPIED})
            codec_args.extend([f"-codec:{output_stream_index}", "copy"])

        output_stream_index += 1

    ffmpeg_args.extend(map_args)
    ffmpeg_args.extend(codec_args)
    ffmpeg_args.extend(["-f", "mp4", "-bsf:a", "aac_adtstoasc", str(output_file)])

    # Execute the FFmpeg command
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    # Create the final ConvertedVideoFile object
    final_converted_file = ConvertedVideoFile(
        path=output_file, stream_sources=new_stream_sources
    )

    # Verification of the re-encoded file is complex and handled by the caller if needed.

    # Log quality metrics for re-encoded streams
    for i, source in final_converted_file.stream_sources.items():
        if source.conversion_type == ConversionType.RE_ENCODED:
            metrics = get_audio_quality_metrics(
                original_file=source.source_video_file.path,
                re_encoded_file=final_converted_file.path,
                audio_stream_index=i,
            )
            if metrics:
                log_parts = [
                    f"{k}={v:.2f}dB"
                    for k, v in metrics._asdict().items()
                    if v is not None
                ]
                if log_parts:
                    logger.info(f"Audio quality for stream {i}: {', '.join(log_parts)}")

    return final_converted_file
