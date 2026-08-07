"""Auto-merge must never be able to merge a pull request whose checks are red.

This is the single assumption every other control in the routine-change lane rests on.
`dependabot-auto-merge.yml` is safe *because* it runs `gh pr merge --auto`, which asks
GitHub to merge when the required checks pass and hands enforcement to GitHub. The
workflow never inspects CI, and therefore cannot get CI wrong. Given that, the worst a
broken merge rule can do is merge something green -- which is what makes it acceptable
for the rule itself to land unattended (ADR-0016, and the routine-change lane built on
it).

Remove `--auto`, or add `--admin`, and that assumption is gone: the workflow merges
whatever it is pointed at. It is a one-word edit, it passes every other check in this
repository, and a human reviewer would not reliably catch it in a diff. So the guard is
here, in the required check, rather than in a person's attention -- which also puts it
*inside* the bound it protects instead of outside it.

Modelled on orchestrator's `tests/architecture/test_no_automatic_merge.py`, which forbids
merging outright. This repository legitimately merges, so the rule is different: any merge
must delegate enforcement to GitHub.

BYTE-IDENTICAL across intent-packages, project-standards, security-standards and
factory-runner; infraops-mcp-server carries the vitest equivalent. Change it in one place
and you have changed a rule the others still enforce -- change it everywhere or nowhere.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
AUTO_MERGE_WORKFLOW = WORKFLOWS / "dependabot-auto-merge.yml"

# Ways to merge that do NOT go through GitHub's required-check enforcement.
#   --admin                     gh pr merge, explicitly bypassing branch protection
#   mergePullRequest            the GraphQL mutation, which merges directly
#   pulls/{n}/merge             the REST endpoint, likewise
# `enablePullRequestAutoMerge` would be equivalent to `--auto` and is still refused: if
# the GraphQL route is ever wanted, take that decision openly rather than by having a
# guard fail to mention it. ADR-0016 made the same call for orchestrator's guard.
BYPASS_PATTERNS = (
    re.compile(r"--admin\b"),
    re.compile(r"\bmergePullRequest\b"),
    re.compile(r"\bmerge_pull_request\b"),
    re.compile(r"\benablePullRequestAutoMerge\b"),
    re.compile(r"pulls/[^\s\"']*/merge\b"),
)

MERGE_COMMAND = re.compile(r"gh\s+pr\s+merge\b")


def _logical_lines(text: str) -> list[str]:
    """Join shell line-continuations, so a flag on the next line still belongs to it."""
    return re.sub(r"\\\n\s*", " ", text).splitlines()


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


def test_the_auto_merge_workflow_exists() -> None:
    """A vacuous pass is the failure mode this guard exists to avoid.

    If auto-merge is ever withdrawn from this repository that is a decision worth making
    visibly -- delete this assertion in the same change, and say why.
    """
    assert AUTO_MERGE_WORKFLOW.is_file(), (
        f"{AUTO_MERGE_WORKFLOW.name} is missing. ADR-0016 puts it here deliberately; "
        "removing it silently turns every assertion below into a vacuous pass."
    )


def test_every_merge_delegates_enforcement_to_github() -> None:
    offenders: list[str] = []
    for path in _workflow_files():
        for number, line in enumerate(_logical_lines(path.read_text(encoding="utf-8")), 1):
            if MERGE_COMMAND.search(line) and "--auto" not in line:
                offenders.append(f"{path.name}:{number}: merges without --auto -- {line.strip()}")
    assert not offenders, (
        "A merge that does not pass --auto merges immediately, without GitHub checking "
        "anything. Every control in the routine-change lane assumes this cannot happen.\n"
        + "\n".join(offenders)
    )


def test_no_workflow_can_bypass_required_checks() -> None:
    offenders: list[str] = []
    for path in _workflow_files():
        for number, line in enumerate(_logical_lines(path.read_text(encoding="utf-8")), 1):
            for pattern in BYPASS_PATTERNS:
                if pattern.search(line):
                    offenders.append(
                        f"{path.name}:{number}: {pattern.pattern!r} bypasses required "
                        f"checks -- {line.strip()}"
                    )
    assert not offenders, (
        "These merge past branch protection rather than through it:\n" + "\n".join(offenders)
    )
