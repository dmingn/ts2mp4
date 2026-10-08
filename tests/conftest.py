"""Pytest configuration file."""

from pathlib import Path

import pytest

from tests.helpers import StubVideoFile
from ts2mp4.ffprobe_schema import FFprobeOutput, FFprobeStream
from ts2mp4.video_file import VideoFile

ALLOWED_MARKERS = {"unit", "integration", "e2e"}


def pytest_collection_modifyitems(
    session: pytest.Session, items: list[pytest.Item]
) -> None:
    """Validate that every test is marked with exactly one of the allowed markers."""
    sorted_markers = sorted(list(ALLOWED_MARKERS))

    for item in items:
        markers = {marker.name for marker in item.iter_markers()}
        intersecting_markers = markers.intersection(ALLOWED_MARKERS)

        if len(intersecting_markers) == 0:
            pytest.fail(
                f"Test item '{item.nodeid}' is missing a required mark. "
                "Please add one of: "
                f"@pytest.mark.{', @pytest.mark.'.join(sorted_markers)}"
            )
        elif len(intersecting_markers) > 1:
            pytest.fail(
                f"Test item '{item.nodeid}' has multiple "
                f"classification marks: {intersecting_markers}. "
                "Please specify exactly one of: "
                f"@pytest.mark.{', @pytest.mark.'.join(sorted_markers)}"
            )


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory path."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def ts_file(project_root: Path) -> Path:
    """Return the path to the test TS file."""
    return project_root / "tests" / "assets" / "test_video.ts"


@pytest.fixture
def mkv_file(project_root: Path) -> Path:
    """Return the path to the test MKV file."""
    return project_root / "tests" / "assets" / "test_video.mkv"


@pytest.fixture(scope="session")
def mixed_surround_ts_file(project_root: Path) -> Path:
    """Return the path to the test TS file whose audio switches from stereo to 5.1ch."""
    return project_root / "tests" / "assets" / "test_mixed_surround.ts"


@pytest.fixture
def mixed_surround_mkv_file(project_root: Path) -> Path:
    """Return the path to the MKV file converted from the mixed surround TS file."""
    return project_root / "tests" / "assets" / "test_mixed_surround.mkv"


@pytest.fixture
def mock_video_file(tmp_path: Path) -> VideoFile:
    """Mock VideoFile object for ts2mp4 tests."""
    dummy_file = tmp_path / "test.ts"
    dummy_file.touch()

    return StubVideoFile(
        path=dummy_file,
        stub_probe=FFprobeOutput(
            streams=(
                FFprobeStream(codec_type="video", index=0),
                FFprobeStream(codec_type="audio", index=1, channels=2),
                FFprobeStream(codec_type="audio", index=2, channels=6),
            )
        ),
    )
