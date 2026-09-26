"""Shared test helpers."""

from typing import Generic

from pydantic import BaseModel

from ts2mp4.ffprobe_schema import FFprobeOutput
from ts2mp4.stream_source import ConvertedVideoFile, StreamSourcesT
from ts2mp4.video_file import Stream, VideoFile


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
    _StubProbe, ConvertedVideoFile[StreamSourcesT], Generic[StreamSourcesT]
):
    """A ConvertedVideoFile whose probe result is given at construction."""
