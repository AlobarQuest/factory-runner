"""WS-P2.23 part C, end to end: an orchestrator ahead of this runner is survivable AND visible.

Two halves, and both are load-bearing. The runner must not die on a brief key it does not
declare -- that killed every dispatch in the estate for a day from 2026-07-30. And it must
not shrug either: the defect being guarded against is invisibility, and plain relaxation
would have produced exactly that.

So the drift is announced where the brief is parsed, and recorded where the orchestrator
keeps things. Reuses the FakeClient + monkeypatched `_run_command` harness from
tests/test_cli.py, as tests/test_evidence_pack_comment.py and tests/test_cost_emit.py do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import _finalization_authority, _runner_brief
from typer.testing import CliRunner, Result

from factory_runner.cli import _fetched_brief, app
from factory_runner.models import RunnerBrief

_PR_URL = "https://github.com/AlobarQuest/orchestrator/pull/99"


def _brief_from_a_newer_orchestrator() -> RunnerBrief:
    """The golden brief plus two keys this revision has never heard of."""
    payload = _runner_brief().model_dump()
    payload["provenance"] = {"emitted_by": "orchestrator"}
    payload["cadence"] = 3
    return RunnerBrief.model_validate(payload)


class _StubClient:
    def __init__(self, brief: RunnerBrief) -> None:
        self._brief = brief

    def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
        return self._brief


def test_the_parse_site_names_every_key_it_did_not_recognise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    brief = _brief_from_a_newer_orchestrator()

    returned = _fetched_brief(_StubClient(brief), "unit-1")  # type: ignore[arg-type]

    message = capsys.readouterr().err
    assert "cadence" in message
    assert "provenance" in message
    assert "behind the orchestrator" in message
    assert returned.work_unit.id == brief.work_unit.id


def test_an_up_to_date_runner_says_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """A report that fires on every run is noise, and noise is how a report stops being read."""
    _fetched_brief(_StubClient(_runner_brief()), "unit-1")  # type: ignore[arg-type]

    assert capsys.readouterr().err == ""


def test_every_brief_fetch_goes_through_the_reporting_parse_site() -> None:
    """A second, unreported fetch path would silently reopen the invisibility.

    Asserted against the source because that is the only way to see a call site that
    was never added -- no test of behaviour can fail for a branch nobody wrote.
    """
    source = Path("src/factory_runner/cli.py").read_text()
    reporting_site = source.split("def _fetched_brief")[1].split("\ndef ")[0]

    assert source.count("client.get_runner_brief(") == 1
    assert "client.get_runner_brief(" in reporting_site


def _write_finalize_workspace(tmp_path: Path, brief: RunnerBrief) -> None:
    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 1,
                "claim_id": "claim-1",
                "context_snapshot_id": "snapshot-1",
                "lease_token": "lease-redacted",
                "package_revision_id": "rev-1",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )


class _RecordingClient:
    _brief: RunnerBrief

    def __init__(self, calls: list[tuple[str, dict[str, object]]], **_kwargs: object) -> None:
        self._calls = calls

    def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
        return self._brief

    def list_evidence(self, _unit_id: str) -> list[dict[str, object]]:
        return []

    def pr_binding(self, unit_id: str, **payload: object) -> dict[str, object]:
        return {"pr_number": payload["pr_number"]}

    def get_evidence_pack_markdown(self, unit_id: str) -> str:
        return "# Evidence Pack\n"

    def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        self._calls.append(("submit_evidence", {"unit_id": unit_id, "payload": payload}))
        return {"id": "evidence-1"}

    def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
        return {}

    def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"unit_id": unit_id, "state": "submitted", "version": 6}


def _make_client_class(brief: RunnerBrief, calls: list[tuple[str, dict[str, object]]]) -> type:
    class Client(_RecordingClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(calls, **kwargs)
            self._brief = brief

    return Client


def _fake_run_command(command: list[str], **_kwargs: object) -> str:
    if command[:3] == ["git", "status", "--porcelain"]:
        return " M src/example.py\n"
    if command[:3] == ["git", "rev-parse", "HEAD"]:
        return "abc123\n"
    if command[:3] == ["gh", "pr", "create"]:
        return f"{_PR_URL}\n"
    if command[:3] == ["gh", "pr", "view"]:
        return "99\n"
    if command[:2] == ["gh", "api"]:
        return "[]"
    return ""


def _run_finalize(tmp_path: Path) -> Result:
    return CliRunner().invoke(
        app,
        [
            "finalize-run",
            "--orchestrator-url",
            "https://sds.alobar.net",
            "--credential-key-id",
            "factory-runner-github",
            "--work-unit-id",
            "unit-1",
            "--workspace-dir",
            str(tmp_path),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )


@pytest.mark.parametrize(
    ("brief_factory", "expected"),
    [
        (_brief_from_a_newer_orchestrator, ["cadence", "provenance"]),
        (_runner_brief, None),
    ],
    ids=["orchestrator-ahead", "in-step"],
)
def test_finalization_records_the_drift_where_the_orchestrator_retains_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    brief_factory: object,
    expected: list[str] | None,
) -> None:
    """`extra="allow"` round-trips the keys through brief.json, so finalize sees what prepare saw.

    The Actions log is not part of the orchestrator's record; the evidence is. This is the
    half that makes the drift survive the run.
    """
    brief = brief_factory()  # type: ignore[operator]
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", _fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    submitted = next(payload for name, payload in calls if name == "submit_evidence")
    evidence = submitted["payload"]["payload"]  # type: ignore[index]
    if expected is None:
        assert "unknown_brief_keys" not in evidence
    else:
        assert evidence["unknown_brief_keys"] == expected
