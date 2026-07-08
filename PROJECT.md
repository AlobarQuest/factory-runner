---
project: factory-runner
foundation: false
status: ws43-local-heavy-pending-merge
owner: Devon
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
- WS-4.3 local-heavy runtime is implemented on branch
  `ws43-local-heavy-runtime` pending Devon merge. It adds manual
  claim/renew/reclaim/finalize commands for approved work units that are too
  large, stateful, multi-repo, or context-heavy for the GitHub-hosted runner.
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
