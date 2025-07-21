import itertools
from pathlib import Path
from typing import NamedTuple

from logzero import logger

from .ffmpeg import execute_ffmpeg
from .hashing import get_stream_md5
from .media_info import Stream, get_media_info


def check_stream_integrity(
    input_file: Path,
    output_file: Path,
    input_stream: Stream,
    output_stream: Stream,
) -> bool:
    """Checks the integrity of a single stream by comparing MD5 hashes.

    Returns:
        True if the stream hashes match and hash generation is successful, False otherwise.
    """
    try:
        input_md5 = get_stream_md5(input_file, input_stream)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for input stream at index {input_stream.index}: {e}"
        )
        return False

    try:
        output_md5 = get_stream_md5(output_file, output_stream)
    except RuntimeError as e:
        logger.warning(
            f"Failed to get MD5 for output stream at index {output_stream.index}: {e}"
        )
        return False

    if input_md5 != output_md5:
        logger.warning(
            f"Mismatch in stream at index {input_stream.index}: "
            f"Input MD5: {input_md5}, Output MD5: {output_md5}"
        )
        return False

    return True


class AudioStreamArgs(NamedTuple):
    """A tuple containing FFmpeg arguments and indices of copied audio streams."""

    ffmpeg_args: list[str]
    copied_audio_stream_indices: list[int]


def _build_re_encode_args(
    audio_stream_index: int, original_audio_stream: Stream
) -> list[str]:
    re_encode_args = [
        "-map",
        f"0:a:{audio_stream_index}",
        f"-codec:a:{audio_stream_index}",
        str(original_audio_stream.codec_name),
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
            integrity_check_passes = check_stream_integrity(
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
    )


def _verify_re_encoded_stream_integrity(
    encoded_file: Path,
    output_file: Path,
    copied_audio_stream_indices: list[int],
) -> None:
    """Verifies the integrity of streams after re-encoding.

    This function checks that the video streams and copied audio streams in the
    output file match the streams in the encoded file by comparing their MD5
    hashes.

    Args:
    ----
        encoded_file: The path to the file that has been encoded but may have
                      audio stream issues.
        output_file: The path where the corrected output file has been saved.
        copied_audio_stream_indices: A list of indices for audio streams that
                                     were copied without re-encoding.

    Raises:
    ------
        RuntimeError: If there's a mismatch in stream counts or if any stream's
            MD5 hash does not match between the encoded and output files.
    """
    logger.info(f"Verifying stream integrity for {output_file.name}")

    encoded_media_info = get_media_info(encoded_file)
    output_media_info = get_media_info(output_file)

    encoded_video_streams = [
        s for s in encoded_media_info.streams if s.codec_type == "video"
    ]
    output_video_streams = [
        s for s in output_media_info.streams if s.codec_type == "video"
    ]

    if len(encoded_video_streams) != len(output_video_streams):
        raise RuntimeError(
            "Mismatch in the number of video streams: "
            f"{len(encoded_video_streams)} in encoded file, "
            f"{len(output_video_streams)} in output file."
        )

    for encoded_stream, output_stream in zip(
        encoded_video_streams, output_video_streams
    ):
        if not check_stream_integrity(
            encoded_file, output_file, encoded_stream, output_stream
        ):
            raise RuntimeError(
                f"Video stream integrity check failed for stream at index {encoded_stream.index}"
            )

    encoded_audio_streams = [
        s for s in encoded_media_info.streams if s.codec_type == "audio"
    ]
    output_audio_streams = [
        s for s in output_media_info.streams if s.codec_type == "audio"
    ]

    for stream_index in copied_audio_stream_indices:
        if not check_stream_integrity(
            encoded_file,
            output_file,
            encoded_audio_streams[stream_index],
            output_audio_streams[stream_index],
        ):
            raise RuntimeError(
                "Copied audio stream integrity check failed for stream at index "
                f"{stream_index}"
            )

    logger.info("Stream integrity verified successfully.")


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

    _verify_re_encoded_stream_integrity(
        encoded_file=encoded_file,
        output_file=output_file,
        copied_audio_stream_indices=audio_stream_args.copied_audio_stream_indices,
    )


def verify_audio_stream_integrity(input_file: Path, output_file: Path) -> None:
    """Verifies the integrity of audio streams by comparing their MD5 hashes.

    This function iterates through all audio streams in the input and output
    files, calculates their MD5 hashes, and compares them. If any pair of
    hashes does not match, or if an audio stream is present in one file but
    not the other, it raises a RuntimeError.

    Args:
    ----
        input_file: The path to the input file.
        output_file: The path to the output file.

    Raises:
    ------
        RuntimeError: If there's a mismatch in audio stream count, or if any
            audio stream's MD5 hash does not match between the input and
            output files.

    """
    logger.info(
        f"Verifying audio stream integrity for {input_file.name} and {output_file.name}"
    )

    input_media_info = get_media_info(input_file)
    output_media_info = get_media_info(output_file)

    input_audio_streams = [
        s for s in input_media_info.streams if s.codec_type == "audio"
    ]
    output_audio_streams = [
        s for s in output_media_info.streams if s.codec_type == "audio"
    ]

    if len(input_audio_streams) != len(output_audio_streams):
        raise RuntimeError(
            "Mismatch in the number of audio streams: "
            f"{len(input_audio_streams)} in input, "
            f"{len(output_audio_streams)} in output."
        )

    for input_stream, output_stream in zip(input_audio_streams, output_audio_streams):
        if not check_stream_integrity(
            input_file, output_file, input_stream, output_stream
        ):
            raise RuntimeError(
                f"Audio stream integrity check failed for stream at index {input_stream.index}"
            )

    logger.info("Audio stream integrity verified successfully. All MD5 hashes match.")
