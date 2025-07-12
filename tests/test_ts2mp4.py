import importlib.metadata
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ts2mp4.ts2mp4 import _get_ts2mp4_version, ts2mp4


def test_get_ts2mp4_version_success(mocker):
    mocker.patch("importlib.metadata.version", return_value="1.2.3")
    assert _get_ts2mp4_version() == "1.2.3"


def test_get_ts2mp4_version_package_not_found(mocker):
    mocker.patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    )
    assert _get_ts2mp4_version() == "Unknown"


@pytest.fixture
def mock_dependencies(mocker):
    mock_subprocess_run = mocker.patch(
        "ts2mp4.ts2mp4.subprocess.run", return_value=MagicMock(stdout="", stderr="")
    )
    mocker.patch("pathlib.Path.exists", return_value=False)
    mocker.patch("pathlib.Path.resolve", return_value=Path("test.ts"))
    mocker.patch(
        "pathlib.Path.with_suffix", side_effect=lambda suffix: Path(f"test{suffix}")
    )
    mocker.patch("pathlib.Path.stat", return_value=MagicMock(st_size=100))
    mocker.patch("pathlib.Path.replace")
    mocker.patch("logzero.logfile")
    mocker.patch("ts2mp4.ts2mp4.verify_audio_stream_integrity")
    return mock_subprocess_run


@pytest.mark.parametrize(
    "crf_value, preset_value",
    [
        (20, "slow"),
        (25, "fast"),
    ],
)
def test_ts2mp4_custom_crf_preset(mock_dependencies, crf_value, preset_value):
    """Test ts2mp4 with custom crf and preset values."""
    ts_path = Path("test.ts")
    ts2mp4(
        input_file=ts_path,
        output_file=ts_path.with_suffix(".mp4.part"),
        crf=crf_value,
        preset=preset_value,
    )
    subprocess_run_mock = mock_dependencies
    expected_command = [
        "ffmpeg",
        "-fflags",
        "+discardcorrupt",
        "-y",
        "-i",
        str(ts_path.resolve()),
        "-f",
        "mp4",
        "-vsync",
        "1",
        "-vf",
        "bwdif",
        "-codec:v",
        "libx265",
        "-crf",
        str(crf_value),
        "-preset",
        preset_value,
        "-codec:a",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        str(ts_path.with_suffix(".mp4.part")),
    ]
    subprocess_run_mock.assert_any_call(
        args=expected_command, check=True, capture_output=True, text=True
    )
