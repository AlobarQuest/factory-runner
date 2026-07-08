from factory_runner.models import RunnerBrief
from factory_runner.pr_body import render_pr_body


def test_pr_body_contains_required_contract() -> None:
    brief = RunnerBrief.model_validate(
        {
            "work_unit": {
                "id": "unit-1",
                "state": "ready",
                "version": 3,
                "title": "Do work",
                "outcome": "Work done",
                "required_capability": "repository_write",
                "max_attempts": 3,
            },
            "package": {
                "id": "pkg",
                "revision_id": "rev-1",
                "revision": 1,
                "content_hash": "sha256:abc",
                "source_repository": "AlobarQuest/orchestrator",
                "source_path": "package.yaml",
                "source_commit": "abc123",
            },
            "authority": {
                "fingerprint": "fingerprint",
                "envelope": {"capabilities": {"repo.read": "allowed"}, "constraints": {}},
            },
            "acceptance_criteria": [],
            "readiness": {"status": "ready", "reasons": []},
            "target": {"repository": "AlobarQuest/orchestrator"},
            "standing_context": {},
        }
    )

    body = render_pr_body(
        brief,
        runner_version="0.1.0",
        risk_surface="docs-only",
        verification=["make check: passed"],
        evidence_refs=["evidence:abc"],
    )

    assert "Work unit: `unit-1`" in body
    assert "Package: `pkg` revision `1`" in body
    assert "Authority fingerprint: `fingerprint`" in body
    assert "Runner cannot merge this PR." in body


def test_pr_body_normalizes_multiline_list_items() -> None:
    brief = RunnerBrief.model_validate(
        {
            "work_unit": {
                "id": "unit-1",
                "state": "ready",
                "version": 3,
                "title": "Do work",
                "outcome": "Work done",
                "required_capability": "repository_write",
                "max_attempts": 3,
            },
            "package": {
                "id": "pkg",
                "revision_id": "rev-1",
                "revision": 1,
                "content_hash": "sha256:abc",
                "source_repository": "AlobarQuest/orchestrator",
                "source_path": "package.yaml",
                "source_commit": "abc123",
            },
            "authority": {
                "fingerprint": "fingerprint",
                "envelope": {"capabilities": {"repo.read": "allowed"}, "constraints": {}},
            },
            "acceptance_criteria": [],
            "readiness": {"status": "ready", "reasons": []},
            "target": {"repository": "AlobarQuest/orchestrator"},
            "standing_context": {},
        }
    )

    body = render_pr_body(
        brief,
        runner_version="0.1.0",
        risk_surface="docs-only",
        verification=["make check\n- injected"],
        evidence_refs=["evidence:abc\r\nsecond line"],
    )

    assert "- make check - injected" in body
    assert "- evidence:abc second line" in body
    assert "make check\n- injected" not in body
    assert "evidence:abc\r\nsecond line" not in body
