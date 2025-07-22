"""Pytest configuration file."""

from pathlib import Path

import pytest

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
def mp4_file(project_root: Path) -> Path:
    """Return the path to the test MP4 file."""
    return project_root / "tests" / "assets" / "test_video.mp4"
