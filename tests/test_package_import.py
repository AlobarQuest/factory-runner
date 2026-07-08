import factory_runner


def test_package_exposes_version() -> None:
    assert factory_runner.__version__ == "0.1.0"
