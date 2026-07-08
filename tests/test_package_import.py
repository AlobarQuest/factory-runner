import factory_runner
from factory_runner.cli import app


def test_package_exposes_version() -> None:
    assert factory_runner.__version__ == "0.1.0"


def test_cli_app_importable() -> None:
    assert app is not None
