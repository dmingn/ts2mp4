"""Unit tests for the ffmpeg_input_args module."""

from pathlib import Path

import pytest

from ts2mp4.ffmpeg_input_args import build_input_args, build_zero_based_input_args


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


@pytest.mark.unit
@pytest.mark.parametrize(
    "start_time, expected_offset_args",
    [
        pytest.param(100.5, ["-itsoffset", "-100.5"], id="start_time"),
        pytest.param(0.0, [], id="zero_start_time"),
        pytest.param(None, [], id="no_start_time"),
    ],
)
def test_build_zero_based_input_args_shifts_the_input_by_its_start_time(
    start_time: float | None, expected_offset_args: list[str]
) -> None:
    """build_zero_based_input_args shifts the input so that the file starts at zero."""
    # Act
    args = build_zero_based_input_args(Path("in.ts"), start_time)

    # Assert
    assert args == [*expected_offset_args, *build_input_args(Path("in.ts"))]
