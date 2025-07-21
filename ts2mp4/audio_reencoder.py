import itertools
from pathlib import Path
from typing import NamedTuple

from logzero import logger

from .ffmpeg import execute_ffmpeg, is_libfdk_aac_available
from .media_info import Stream, get_media_info
from .quality_check import get_audio_quality_metrics
from .stream_integrity import compare_stream_hashes, verify_streams


class AudioStreamArgs(NamedTuple):
    """A tuple containing FFmpeg arguments and indices of copied/re-encoded audio streams."""

    ffmpeg_args: list[str]
    copied_audio_stream_indices: list[int]
    re_encoded_audio_stream_indices: list[int]


def _build_re_encode_args(
    audio_stream_index: int, original_audio_stream: Stream
) -> list[str]:
    codec_name = str(original_audio_stream.codec_name)
    if original_audio_stream.codec_name == "aac":
        if is_libfdk_aac_available():
            codec_name = "libfdk_aac"
        else:
            logger.warning(
                "libfdk_aac is not available. Falling back to the default AAC encoder."
            )

    re_encode_args = [
        "-map",
        f"0:a:{audio_stream_index}",
        f"-codec:a:{audio_stream_index}",
        codec_name,
    ]
    if original_audio_stream.sample_rate is not None:
        re_encode_args.extend(
            [
                f"-ar:a:{audio_stream_index}",
                str(original_audio_stream.sample_rate),
            ]
        )
    if original_audio_stream.channels is not None:
        re_encode_args.extend(
            [
                f"-ac:a:{audio_stream_index}",
                str(original_audio_stream.channels),
            ]
        )
    if original_audio_stream.profile is not None:
        profile_map = {"LC": "aac_low"}
        profile = profile_map.get(
            original_audio_stream.profile, original_audio_stream.profile
        )
        re_encode_args.extend(
            [
                f"-profile:a:{audio_stream_index}",
                profile,
            ]
        )
    if original_audio_stream.bit_rate is not None:
        re_encode_args.extend(
            [
                f"-b:a:{audio_stream_index}",
                str(original_audio_stream.bit_rate),
            ]
        )
    re_encode_args.extend([f"-bsf:a:{audio_stream_index}", "aac_adtstoasc"])
    return re_encode_args


def _build_args_for_audio_streams(
    original_file: Path, encoded_file: Path
) -> AudioStreamArgs:
    """Builds FFmpeg arguments and identifies copied audio streams.

    It assumes that the order of audio streams is preserved between the
    original and encoded files.
    """
    original_media_info = get_media_info(original_file)
    encoded_media_info = get_media_info(encoded_file)

    original_audio_streams = [
        stream for stream in original_media_info.streams if stream.codec_type == "audio"
    ]
    encoded_audio_streams = [
        stream for stream in encoded_media_info.streams if stream.codec_type == "audio"
    ]

    ffmpeg_args = []
    copied_audio_stream_indices = []
    re_encoded_audio_stream_indices = []
    for audio_stream_index, (original_audio_stream, encoded_audio_stream) in enumerate(
        itertools.zip_longest(original_audio_streams, encoded_audio_streams)
    ):
        if original_audio_stream is None:
            # Unexpected: Original file has fewer audio streams than expected.
            raise RuntimeError(
                f"Encoded file {encoded_file.name} has more audio streams than the original {original_file.name}."
            )

        integrity_check_passes = False
        if encoded_audio_stream is not None:
            integrity_check_passes = compare_stream_hashes(
                input_file=original_file,
                output_file=encoded_file,
                input_stream=original_audio_stream,
                output_stream=encoded_audio_stream,
            )

        if not integrity_check_passes:
            if original_audio_stream.codec_name is None:
                # Unexpected: Original file's audio stream lacks a codec name.
                raise RuntimeError(
                    f"Original audio stream at index {audio_stream_index} has no codec name."
                )
            if original_audio_stream.codec_name != "aac":
                raise NotImplementedError(
                    "Re-encoding is currently only supported for aac audio codec."
                )

            logger.warning(
                f"Re-encoding audio stream at index {audio_stream_index} "
                f"from {original_file.name} due to mismatch or absence in {encoded_file.name}."
            )

            ffmpeg_args.extend(
                _build_re_encode_args(audio_stream_index, original_audio_stream)
            )
            re_encoded_audio_stream_indices.append(audio_stream_index)
        else:
            ffmpeg_args.extend(
                [
                    "-map",
                    f"1:a:{audio_stream_index}",  # Use encoded audio stream
                    f"-codec:a:{audio_stream_index}",
                    "copy",  # Copy codec without re-encoding
                ]
            )
            copied_audio_stream_indices.append(audio_stream_index)

    return AudioStreamArgs(
        ffmpeg_args=ffmpeg_args,
        copied_audio_stream_indices=copied_audio_stream_indices,
        re_encoded_audio_stream_indices=re_encoded_audio_stream_indices,
    )


def re_encode_mismatched_audio_streams(
    original_file: Path, encoded_file: Path, output_file: Path
) -> None:
    """Re-encodes mismatched audio streams from an original file to a new output file.

    This function identifies audio streams that are either missing in the encoded
    file or have different content compared to the original file. It then
    generates a new video file by:
    - Copying the video stream from the already encoded file.
    - Copying matching audio streams from the encoded file.
    - Re-encoding mismatched or missing audio streams from the original file
      using their original codecs.
    - Copying subtitle streams from the encoded file.

    Args:
    ----
        original_file: The path to the original source file (e.g., .ts).
        encoded_file: The path to the file that has been encoded but may have
                      audio stream issues.
        output_file: The path where the corrected output file will be saved.
    """

    def _verify_integrity(
        copied_audio_stream_indices: list[int],
    ) -> None:
        """Verifies the integrity of streams after re-encoding."""
        logger.info(f"Verifying stream integrity for {output_file.name}")

        verify_streams(encoded_file, output_file, "video")
        verify_streams(
            encoded_file,
            output_file,
            "audio",
            type_specific_stream_indices=copied_audio_stream_indices,
        )

        logger.info("Stream integrity verified successfully.")

    audio_stream_args = _build_args_for_audio_streams(
        original_file=original_file, encoded_file=encoded_file
    )

    if not audio_stream_args.ffmpeg_args:
        logger.info("No audio streams require re-encoding.")
        return

    ffmpeg_args = [
        "-hide_banner",
        "-nostats",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(original_file),
        "-i",
        str(encoded_file),
        # for video streams
        "-map",
        "1:v",  # Use video stream from encoded_file
        "-codec:v",
        "copy",  # Copy video codec without re-encoding
        # for audio streams
        *audio_stream_args.ffmpeg_args,
        # for subtitles
        "-map",
        "1:s?",  # Use subtitle streams from encoded_file if available
        "-codec:s",
        "copy",  # Copy subtitle codec without re-encoding
        # output file
        str(output_file),
    ]

    # Execute the FFmpeg command
    result = execute_ffmpeg(ffmpeg_args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")

    _verify_integrity(
        copied_audio_stream_indices=audio_stream_args.copied_audio_stream_indices,
    )

    for audio_stream_index in audio_stream_args.re_encoded_audio_stream_indices:
        metrics = get_audio_quality_metrics(
            original_file=original_file,
            re_encoded_file=output_file,
            audio_stream_index=audio_stream_index,
        )
        if metrics:
            log_parts = []
            if metrics.apsnr is not None:
                log_parts.append(f"APSNR={metrics.apsnr:.2f}dB")
            if metrics.asdr is not None:
                log_parts.append(f"ASDR={metrics.asdr:.2f}dB")
            if log_parts:
                logger.info(
                    f"Audio quality for stream {audio_stream_index}: {', '.join(log_parts)}"
                )
