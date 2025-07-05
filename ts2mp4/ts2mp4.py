import hashlib
import subprocess
from pathlib import Path


def _get_audio_stream_md5(file_path: Path) -> str:
    """Calculates the MD5 hash of the decoded audio stream of a given file.

    Args:
        file_path: The path to the input file.

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
        "0:a",  # Select the first audio stream
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

    # Get MD5 hash of the input audio stream
    input_audio_md5 = _get_audio_stream_md5(ts)

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

    # Get MD5 hash of the output audio stream (from the .part file)
    output_audio_md5 = _get_audio_stream_md5(mp4_part)

    # Assert that the MD5 hashes match
    if input_audio_md5 != output_audio_md5:
        raise RuntimeError(
            f"Audio stream MD5 mismatch! Input: {input_audio_md5}, Output: {output_audio_md5}"
        )

    mp4_part.replace(mp4)
