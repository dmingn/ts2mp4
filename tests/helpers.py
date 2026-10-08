"""Shared test helpers."""

from collections.abc import AsyncIterator, Sequence
from fractions import Fraction
from typing import Generic

from pydantic import BaseModel

from ts2mp4.conversion_plan import FileConversionPlanT
from ts2mp4.converted_video_file import ConvertedVideoFile
from ts2mp4.ffmpeg import FFmpegResult
from ts2mp4.ffprobe_schema import FFprobeOutput
from ts2mp4.video_file import Stream, VideoFile

TS_TIME_BASE = Fraction(1, 90000)


class FakeFFmpegRunner:
    """An FFmpegRunner that records the arguments of each call and returns fixed output."""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr_lines: Sequence[str] = (),
        out_seconds: Sequence[float] = (),
        error: Exception | None = None,
    ) -> None:
        """Return the fixed output from every call, or raise ``error``."""
        self.stdout = stdout
        self.stderr_lines = tuple(stderr_lines)
        self.out_seconds = tuple(out_seconds)
        self.error = error
        self.calls: list[list[str]] = []
        self.piped_calls: list[tuple[list[str], list[str]]] = []

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

    async def stream_stderr_piped(
        self, source_args: list[str], args: list[str]
    ) -> AsyncIterator[str]:
        """Record ``source_args`` and ``args`` and yield the fixed stderr lines."""
        self.piped_calls.append((source_args, args))
        if self.error is not None:
            raise self.error

        for line in self.stderr_lines:
            yield line

    async def stream_out_seconds(self, args: list[str]) -> AsyncIterator[float]:
        """Record ``args`` and yield the fixed output seconds."""
        self.calls.append(args)
        if self.error is not None:
            raise self.error

        for out_seconds in self.out_seconds:
            yield out_seconds


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
