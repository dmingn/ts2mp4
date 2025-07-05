import subprocess
from pathlib import Path

from .audio_integrity import verify_audio_stream_integrity


def ts2mp4(ts: Path):
    ts = ts.resolve()
    mp4 = ts.with_suffix(".mp4")
    mp4_part = ts.with_suffix(".mp4.part")

    if mp4.exists():
        return

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

    verify_audio_stream_integrity(ts, mp4_part)

    mp4_part.replace(mp4)
