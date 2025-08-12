"""Re-encodes audio streams that have integrity issues."""

import itertools
from pathlib import Path
from typing import Optional

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


def _build_re_encode_ffmpeg_args(
    output_path: Path,
    stream_sources: dict[int, StreamSource],
) -> list[str]:
    """Build FFmpeg arguments for re-encoding audio streams."""
    # Group sources by input file
    source_files = {s.source_video_file.path for s in stream_sources.values()}
    input_files = sorted(list(source_files))
    input_map = {path: i for i, path in enumerate(input_files)}

    map_args = []
    codec_args = []

    video_source = next(
        s
        for s in stream_sources.values()
        if s.source_video_file.get_stream_by_index(s.source_stream_index).codec_type
        == "video"
    )
    video_input_index = input_map[video_source.source_video_file.path]
    map_args.extend(["-map", f"{video_input_index}:{video_source.source_stream_index}"])
    codec_args.extend(["-codec:v", "copy"])

    for stream_index, source in stream_sources.items():
        if stream_index == 0:  # Already handled video
            continue

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

            if original_stream.sample_rate is not None:
                codec_args.extend(
                    [f"-ar:{stream_index}", str(original_stream.sample_rate)]
                )
            if original_stream.channels is not None:
                codec_args.extend(
                    [f"-ac:{stream_index}", str(original_stream.channels)]
                )
            if original_stream.profile is not None:
                profile_map = {"LC": "aac_low"}
                profile = profile_map.get(
                    original_stream.profile, original_stream.profile
                )
                codec_args.extend([f"-profile:{stream_index}", profile])
            if original_stream.bit_rate is not None:
                codec_args.extend([f"-b:{stream_index}", str(original_stream.bit_rate)])
            codec_args.extend([f"-bsf:{stream_index}", "aac_adtstoasc"])

    return (
        ["-hide_banner", "-nostats", "-fflags", "+discardcorrupt", "-y"]
        + [arg for path in input_files for arg in ("-i", str(path))]
        + map_args
        + codec_args
        + ["-f", "mp4", str(output_path)]
    )


def re_encode_mismatched_audio_streams(
    original_file: VideoFile,
    encoded_file: ConvertedVideoFile,
    output_file: Path,
) -> Optional[ConvertedVideoFile]:
    """Re-encodes mismatched audio streams from an original file to a new output file."""
    video_stream = next(
        s for s in encoded_file.media_info.streams if s.codec_type == "video"
    )

    new_stream_sources = {
        0: encoded_file.stream_sources[video_stream.index].model_copy(
            update={"conversion_type": ConversionType.COPIED}
        )
    }

    needs_re_encoding = False
    for i, (original_audio, encoded_audio) in enumerate(
        itertools.zip_longest(original_file.audio_streams, encoded_file.audio_streams)
    ):
        output_stream_index = i + 1

        if original_audio is None:
            raise RuntimeError("Encoded file has more audio streams than original.")

        integrity_check_passes = False
        if encoded_audio is not None:
            integrity_check_passes = compare_stream_hashes(
                original_file, encoded_file, original_audio, encoded_audio
            )

        if integrity_check_passes:
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
        logger.info("No audio streams require re-encoding.")
        return None

    ffmpeg_args = _build_re_encode_ffmpeg_args(output_file, new_stream_sources)
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    # After re-encoding, verify stream integrity
    re_encoded_video = ConvertedVideoFile(
        path=output_file, stream_sources=new_stream_sources
    )

    copied_audio_indices = [
        i
        for i, s in new_stream_sources.items()
        if i > 0 and s.conversion_type == ConversionType.COPIED
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

    # Log quality metrics for re-encoded streams
    for i, source in new_stream_sources.items():
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
