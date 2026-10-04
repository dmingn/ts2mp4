"""Unit tests for the ffmpeg_input_args module."""

from pathlib import Path

import pytest

from ts2mp4.ffmpeg_input_args import build_input_args


@pytest.mark.unit
def test_build_input_args_puts_probe_options_before_input() -> None:
    """build_input_args places the probe options before ``-i`` so they apply to the input."""
    # Act
    args = build_input_args(Path("in.ts"))

    # Assert
    probe_options = args[: args.index("-i")]
    assert args[-2:] == ["-i", "in.ts"]
    assert "-analyzeduration" in probe_options
    assert "-probesize" in probe_options
