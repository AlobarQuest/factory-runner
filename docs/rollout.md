# Factory Runner Rollout

## Credential Shape

- Actor ID: `factory-runner`
- Credential key ID: `factory-runner-github`
- Header 1: `X-Credential-Key-Id`
- Header 2: `Authorization: Bearer <token from GitHub secret>`

## Secret Rules

- Raw tokens stay only in BWS and GitHub Actions secrets.
- Values are piped from BWS to `gh secret set`.
- Values are never written to tracked files, prompts, logs, package YAML, workflow YAML, or evidence.
- Stable BWS UUIDs are recorded in `.bws-secrets.toml` after creation.

## Durable Credential

- BWS secret UUID: `d2a4c0fc-128b-4bf5-8e25-b481010e1be0`
- GitHub secret: `FACTORY_RUNNER_TOKEN`
- GitHub secret: `FACTORY_RUNNER_CREDENTIAL_KEY_ID`
- Production Coolify env: `ORCHESTRATOR_M2M_CREDENTIALS` stores only the token hash.
- Production image with active runner registry:
  `ghcr.io/alobarquest/orchestrator:656fcef-ws41-registry`

## Pilot Repo: AlobarQuest/orchestrator

- Workflow consumer committed on a branch.
- `FACTORY_RUNNER_TOKEN` secret configured from BWS UUID
  `d2a4c0fc-128b-4bf5-8e25-b481010e1be0`.
- `FACTORY_RUNNER_CREDENTIAL_KEY_ID` secret configured as `factory-runner-github`.
- GitHub Actions permissions allow PR creation but not merge.
- Branch protection keeps Devon as the only merge actor.
- Default verification command: `make check`.

## Preflight Before Live Pilot

```bash
cd ~/Projects/factory-runner
make check
cd ~/Projects/orchestrator
make check
cd ~/Projects/project-standards
uv run portfolio foundation
cd ~/Projects/security-standards
uv run python -m security_scan.cli ~/Projects/factory-runner --category security
```

## Recommended caller pin

`RECOMMENDED_CALLER_PIN` (repo root, single full SHA) declares the reusable-workflow
revision callers should pin their `uses:` to. Bump it deliberately when a workflow
change should propagate; the conformance kit (project-standards `portfolio onboard`)
reads it by pointer and reports any caller behind it. Never point callers at `@main`.

Since WS-P2.23 that pin controls **everything**, and the workflow/CLI split it used to
leave open is gone. `factory-runner.yml` installs `job.workflow_sha` — its own commit,
even when called from another repository — so a caller pinned to commit X runs the
workflow at X and gets the CLI at X. One SHA, three artefacts, by construction rather
than by anyone remembering.

Before, the workflow could only name a commit that already existed, so the workflow and
the CLI it installed were necessarily different revisions and keeping them compatible
was a prose rule nothing enforced. That rule was violated on 2026-07-30 and every
dispatch in the estate died at brief-parse for a day.

Two things follow:

- **Any commit is a valid pin.** There is no separate "does this workflow install a CLI
  that can do the job" question left to get wrong; `RECOMMENDED_CALLER_PIN` is a
  recommendation about which revision to *want*, not a compatibility claim.
- **This file still lags by one commit**, because a commit cannot name its own SHA. Bump
  it in a follow-up commit, exactly as before. What is gone is the lag that mattered.

The orchestrator's PR gate now reads its caller's `uses:` SHA and refuses a change that
would serve a runner brief key the pinned revision does not declare, so the ordering
(runner merges first) is enforced at build time in the repo that would break it.
