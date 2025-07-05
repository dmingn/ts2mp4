import hashlib
import json
import subprocess
from pathlib import Path


def _get_audio_stream_count(file_path: Path) -> int:
    """Returns the number of audio streams in a given file.

    Args:
        file_path: The path to the input file.

    Returns:
        The number of audio streams.

    Raises:
        RuntimeError: If ffprobe fails to get stream information.
    """
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(file_path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffprobe failed to get stream information for {file_path}. Error: {e.stderr.decode()}"
        ) from e

    data = json.loads(result.stdout)
    return sum(
        1 for stream in data.get("streams", []) if stream.get("codec_type") == "audio"
    )


def _get_audio_stream_md5(file_path: Path, stream_index: int) -> str:
    """Calculates the MD5 hash of the decoded audio stream of a given file.

    Args:
        file_path: The path to the input file.
        stream_index: The index of the audio stream to process.

    Returns:
        The MD5 hash of the decoded audio stream as a hexadecimal string.

    Raises:
        RuntimeError: If FFmpeg fails to extract the audio stream.
    """
    command = [
        "ffmpeg",
        "-i",
        str(file_path),
        "-map",
        f"0:a:{stream_index}",
        "-vn",  # No video
        "-f",
        "s16le",  # Output raw signed 16-bit little-endian PCM
        "-",  # Output to stdout
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,  # Raise CalledProcessError for non-zero exit codes
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"FFmpeg failed to get decoded audio stream for {file_path}. Error: {e.stderr.decode()}"
        ) from e

    return hashlib.md5(result.stdout).hexdigest()


def ts2mp4(ts: Path):
    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if mp4.exists():
        return

    # Get the number of audio streams
    audio_stream_count = _get_audio_stream_count(ts)

    # Get MD5 hash of the input audio streams
    input_audio_md5s = [_get_audio_stream_md5(ts, i) for i in range(audio_stream_count)]

    subprocess.run(
        args=[
            "ffmpeg",
            "-fflags",
            "+discardcorrupt",
            "-y",
            "-i",
            str(ts),
            "-f",
            "mp4",
            "-vsync",
            "1",
            "-vf",
            "bwdif",
            "-codec:v",
            "libx265",
            "-crf",
            "22",
            "-codec:a",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(mp4_part),
        ],
        check=True,  # Ensure ffmpeg command raises an error if it fails
    )

    # Get MD5 hash of the output audio streams (from the .part file)
    output_audio_md5s = [
        _get_audio_stream_md5(mp4_part, i) for i in range(audio_stream_count)
    ]

    # Assert that the MD5 hashes match for all streams
    if input_audio_md5s != output_audio_md5s:
        raise RuntimeError(
            f"Audio stream MD5 mismatch! Input: {input_audio_md5s}, Output: {output_audio_md5s}"
        )

    mp4_part.replace(mp4)
