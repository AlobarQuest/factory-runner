from pathlib import Path

import factory_runner
from factory_runner.cli import app


def test_package_exposes_version() -> None:
    assert factory_runner.__version__ == "0.1.0"


def test_cli_app_importable() -> None:
    assert app is not None


def test_local_heavy_docs_cover_safety_contract() -> None:
    docs = Path("docs/local-heavy-runtime.md").read_text()

    required_phrases = [
        "GitHub-hosted factory runner",
        "local-heavy",
        "infra lane",
        "No local-heavy command may merge",
        "BWS",
        "stable UUID",
        "reclaim-expired-claim",
        "private database edits",
        "https://sds.alobar.net",
    ]
    for phrase in required_phrases:
        assert phrase in docs
