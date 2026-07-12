---
project: factory-runner
foundation: false
status: ws43-local-heavy-merged
owner: Devon
name: factory-runner
tier: active
purpose: 'TODO: one-line purpose'
version: 0.1.0
version_source: pyproject
updated: '2026-07-10'
---

# Factory Runner

Reusable GitHub Actions runner pattern for Devon's Software Delivery System.

This repository owns Phase 4 runner surfaces for Devon's Software Delivery
System: the WS-4.1 reusable GitHub-hosted factory runner and the WS-4.3
local-heavy runtime adapter for Devon's machine as a worker.

## Current State

- Repository created for WS-4.1 and merged in `AlobarQuest/factory-runner` PR #1.
- Reusable runner package, authority validation, orchestrator client, evidence
  rendering, preparation CLI, and reusable GitHub Actions workflow are
  implemented.
- Durable runner M2M credential is stored in BWS and configured through
  GitHub/Coolify-managed references for the orchestrator pilot.
- The `AlobarQuest/orchestrator` pilot consumer workflow is merged in
  orchestrator PR #16 but has not been dispatched.
- WS-4.3 local-heavy runtime is merged in `AlobarQuest/factory-runner` PR #3 at
  merge commit `b16f471`. It adds manual claim/renew/reclaim/finalize commands
  for approved work units that are too large, stateful, multi-repo, or
  context-heavy for the GitHub-hosted runner.
- Devon's merge gate is permanent. This repository must not add merge behavior.

## Scope Boundaries

This repository may implement:

- reusable or manually triggered GitHub Actions runner workflow;
- production orchestrator client calls needed by a runner;
- structural tool scoping from an approved authority envelope;
- PR creation with risk/evidence body;
- evidence submission back to the orchestrator;
- manual local-heavy claim, renewal, reclaim, finalization, and operator docs;
- durable runner M2M credential setup through BWS/GitHub/Coolify-managed secret
  references only.

This repository must not implement:

- orchestrator automatic dispatch;
- Phase 5 verifier logic;
- infra-lane linkage;
- tracker canonicalization;
- brain learning or promotion;
- graduation automation;
- automatic merge.

## Local Development

Run:

```bash
uv sync --dev
make check
```

## Rollout State

| Target repo | State | Notes |
|---|---|---|
| `AlobarQuest/orchestrator` | merged, credentialed, not dispatched | First pilot target after approved work unit. |

## Backlog
- [ ] (P1) `finalize-run` hardcodes exit_code: 0 and summary '<cmd>: passed' into the evidence payload for every entry in verification_commands (cli.py ~455-470). It is only truthful because _run_command raises first, and it labels mutators as verifications — the WS-5.1 verifier adjudicates evidence reading 'uv lock --upgrade: passed'. Record the real exit code and distinguish mutators from verifiers. — added 2026-07-10
- [ ] (1) Add CI to factory-runner: it has no workflow at all, yet every repo consumes its reusable workflow via uses: ...@main. A broken main breaks every consumer's factory runs with nothing to catch it. Two such bugs (private-repo install, missing ./scripts wrapper) shipped undetected and blocked WS-6.4 until 2026-07-09. — added 2026-07-10
- [ ] (2) Pin the runner version: callers use 'uses: ...@main' and the workflow installs 'git+...@main', both unpinned. Tagged releases would make the runner version part of the evidence trail and stop a main push instantly changing every consumer's behavior. — added 2026-07-10
- [ ] (P1) Factory-runner PRs are held in GitHub action_required (require-approval-for-contributor gate), so the target repo's named CI check never auto-runs on the PR head — AC-001 evidence ('named check succeeds on head') can't materialize automatically. Fix: open/push PRs with a trusted identity (PAT/deploy key) so runs aren't gated, or add a documented maintainer-approval step. Surfaced by WS-6.4 canary PR #43 (only clearable via Actions UI 'Approve and run'; REST /approve is fork-only). — added 2026-07-10
- [ ] (P1) can_create_pr is computed and never enforced: validate_authority() derives can_create_pr=_allowed(envelope, 'github.pr.create') into RunnerPermissions (authority.py:35), and grep shows NOTHING ever reads it — the runner opens a PR without consulting the permission it just computed. A fifth instance of the WS-P2.15 pattern (a guard nobody calls), this one in factory-runner. Wire it: refuse to open a PR when the envelope does not allow github.pr.create. Until then the capability is validated as a NAME and ignored as a PERMISSION, so any orchestrator-side guard keyed on it means nothing on the worker side. Scoped into WS-P2.16 — added 2026-07-12 — added 2026-07-12
