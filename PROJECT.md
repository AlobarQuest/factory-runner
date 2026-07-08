---
project: factory-runner
foundation: false
status: merged-pilot-ready
owner: Devon
---

# Factory Runner

Reusable GitHub Actions runner pattern for Devon's Software Delivery System.

This repository owns Phase 4 WS-4.1: generalizing the proven conformance-runner
pattern into a reusable GitHub-hosted structural sandbox that can claim approved
orchestrator work units, open evidence-bearing PRs, and report evidence back to
the production orchestrator at `https://sds.alobar.net`.

## Current State

- Repository created for WS-4.1 and merged in `AlobarQuest/factory-runner` PR #1.
- Reusable runner package, authority validation, orchestrator client, evidence
  rendering, preparation CLI, and reusable GitHub Actions workflow are
  implemented.
- Durable runner M2M credential is stored in BWS and configured through
  GitHub/Coolify-managed references for the orchestrator pilot.
- The `AlobarQuest/orchestrator` pilot consumer workflow is merged in
  orchestrator PR #16 but has not been dispatched.
- Devon's merge gate is permanent. This repository must not add merge behavior.

## Scope Boundaries

WS-4.1 may implement:

- reusable or manually triggered GitHub Actions runner workflow;
- production orchestrator client calls needed by a runner;
- structural tool scoping from an approved authority envelope;
- PR creation with risk/evidence body;
- evidence submission back to the orchestrator;
- durable runner M2M credential setup through BWS/GitHub/Coolify-managed secret
  references only.

WS-4.1 must not implement:

- orchestrator automatic dispatch;
- Phase 5 verifier logic;
- local-heavy-runtime codification;
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
