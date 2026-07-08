from pathlib import Path

import yaml


def test_workflow_has_no_merge_permission_or_merge_command() -> None:
    workflow = Path(".github/workflows/factory-runner.yml").read_text()

    assert "pull-requests: write" in workflow
    assert "contents: write" in workflow
    assert "gh pr merge" not in workflow
    assert "merge-method" not in workflow


def test_workflow_is_manual_and_reusable_only() -> None:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())

    assert set(data["on"]) == {"workflow_dispatch", "workflow_call"}
    assert "schedule" not in data["on"]
