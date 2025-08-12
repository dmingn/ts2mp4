"""Pytest configuration file."""

from pathlib import Path
from typing import Callable, Optional

import pytest
from pytest_mock import MockerFixture

from ts2mp4.media_info import MediaInfo, Stream
from ts2mp4.video_file import (
    ConversionType,
    ConvertedVideoFile,
    StreamSource,
    VideoFile,
)

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


@pytest.fixture
def video_file_factory(
    tmp_path: Path, mocker: MockerFixture
) -> Callable[..., VideoFile]:
    """Create a factory for creating VideoFile objects for testing."""

    def _factory(
        filename: str = "test.ts", streams: Optional[list[Stream]] = None
    ) -> VideoFile:
        filepath = tmp_path / filename
        filepath.touch()
        if streams:
            mocker.patch(
                "ts2mp4.video_file.get_media_info",
                return_value=MediaInfo(streams=streams),
            )
        return VideoFile(path=filepath)

    return _factory


@pytest.fixture
def converted_video_file_factory(
    video_file_factory: Callable[..., VideoFile],
) -> Callable[..., ConvertedVideoFile]:
    """Create a factory for creating ConvertedVideoFile objects for testing."""

    def _factory(
        filename: str = "converted.mp4",
        source_video_file: Optional[VideoFile] = None,
        stream_sources: Optional[dict[int, StreamSource]] = None,
    ) -> ConvertedVideoFile:
        if source_video_file is None:
            source_video_file = video_file_factory()

        if stream_sources is None:
            stream_sources = {
                0: StreamSource(
                    source_video_file=source_video_file,
                    source_stream_index=0,
                    conversion_type=ConversionType.CONVERTED,
                )
            }

        filepath = source_video_file.path.parent / filename
        filepath.touch()

        return ConvertedVideoFile(path=filepath, stream_sources=stream_sources)

    return _factory
