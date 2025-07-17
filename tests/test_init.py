import importlib.metadata

from pytest_mock import MockerFixture

from ts2mp4 import _get_ts2mp4_version


def test_get_ts2mp4_version_success(mocker: MockerFixture) -> None:
    mocker.patch("importlib.metadata.version", return_value="1.2.3")
    assert _get_ts2mp4_version() == "1.2.3"


def test_get_ts2mp4_version_package_not_found(mocker: MockerFixture) -> None:
    mocker.patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    )
    assert _get_ts2mp4_version() == "Unknown"
