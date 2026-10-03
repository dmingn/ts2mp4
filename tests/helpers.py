"""Shared test helpers."""

from collections.abc import AsyncIterator, Sequence
from typing import Generic

from pydantic import BaseModel

from ts2mp4.conversion_plan import FileConversionPlanT
from ts2mp4.converted_video_file import ConvertedVideoFile
from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.ffprobe_schema import FFprobeOutput
from ts2mp4.video_file import Stream, VideoFile


class FakeFFmpegRunner:
    """An FFmpegRunner that records the arguments of each call and returns fixed output."""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr_lines: Sequence[str] = (),
        error: Exception | None = None,
    ) -> None:
        """Return ``stdout`` and ``stderr_lines`` from every call, or raise ``error``."""
        self.stdout = stdout
        self.stderr_lines = tuple(stderr_lines)
        self.error = error
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> FFmpegResult:
        """Record ``args`` and return the fixed output."""
        self.calls.append(args)
        if self.error is not None:
            raise self.error

        return FFmpegResult(
            stdout=self.stdout, stderr="".join(self.stderr_lines), returncode=0
        )

    async def stream_stdout(self, args: list[str]) -> AsyncIterator[bytes]:
        """Record ``args`` and yield the fixed stdout."""
        self.calls.append(args)
        if self.error is not None:
            raise self.error

        yield self.stdout

    async def stream_stderr(self, args: list[str]) -> AsyncIterator[str]:
        """Record ``args`` and yield the fixed stderr lines."""
        self.calls.append(args)
        if self.error is not None:
            raise self.error

        for line in self.stderr_lines:
            yield line


def stream_at(streams: frozenset[Stream], index: int) -> Stream:
    """Return the stream whose index matches ``index``."""
    return next(stream for stream in streams if stream.index == index)


class _StubProbe(BaseModel):
    """Serve ``probe`` from ``stub_probe`` instead of running ffprobe."""

    stub_probe: FFprobeOutput

    @property
    def probe(self) -> FFprobeOutput:
        """Return the stubbed ffprobe output."""
        return self.stub_probe


class StubVideoFile(_StubProbe, VideoFile):
    """A VideoFile whose probe result is given at construction."""


class StubConvertedVideoFile(
    _StubProbe, ConvertedVideoFile[FileConversionPlanT], Generic[FileConversionPlanT]
):
    """A ConvertedVideoFile whose probe result is given at construction."""
