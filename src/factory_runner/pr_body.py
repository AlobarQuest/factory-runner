from factory_runner.models import RunnerBrief


def _normalize_list_item(item: str) -> str:
    return " ".join(item.split())


def render_pr_body(
    brief: RunnerBrief,
    *,
    runner_version: str,
    risk_surface: str,
    verification: list[str],
    evidence_refs: list[str],
) -> str:
    verification_lines = (
        "\n".join(f"- {_normalize_list_item(item)}" for item in verification) or "- Not run"
    )
    evidence_lines = (
        "\n".join(f"- {_normalize_list_item(item)}" for item in evidence_refs) or "- Not submitted"
    )
    return f"""## Factory Runner Evidence

Work unit: `{brief.work_unit.id}`
Package: `{brief.package.id}` revision `{brief.package.revision}`
Package hash: `{brief.package.content_hash}`
Source commit: `{brief.package.source_commit}`
Runner version: `{runner_version}`
Authority fingerprint: `{brief.authority.fingerprint}`
Risk surface: `{risk_surface}`

## Verification

{verification_lines}

## Orchestrator Evidence

{evidence_lines}

Runner cannot merge this PR.
"""
