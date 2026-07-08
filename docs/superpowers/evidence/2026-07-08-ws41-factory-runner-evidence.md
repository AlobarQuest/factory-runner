# WS-4.1 Factory Runner Evidence

Date: 2026-07-08
Scope: Phase 4 WS-4.1 only

## Delivered

- Created `AlobarQuest/factory-runner` as the WS-4.1 owning repository.
- Implemented authority-envelope validation, including repository, branch, path,
  command, environment, and token-shape constraints.
- Implemented the orchestrator runner client for `https://sds.alobar.net` with
  both `X-Credential-Key-Id` and bearer-token auth support.
- Implemented PR body and evidence payload rendering with lease-token redaction.
- Added `prepare` CLI behavior for fetching one approved work-unit brief and
  writing a runner workspace manifest.
- Added reusable GitHub Actions workflow
  `.github/workflows/factory-runner.yml`.
- Added rollout documentation for BWS/GitHub/Coolify-managed secret references.
- Added orchestrator runner-brief API support in the orchestrator worktree.
- Added manual orchestrator pilot consumer workflow
  `.github/workflows/factory-runner-pilot.yml` in the orchestrator worktree.

## Not Completed In This Session

- Live durable M2M credential creation and GitHub/Coolify secret configuration
  are intentionally deferred to a fresh infra/credential session. This session
  mixed code/repository work with review of hostile external/repo data, so live
  secret and production configuration mutation was not performed.
- No live pilot workflow was dispatched.
- No PR was merged.

## Verification

- `factory-runner`: `make check` passed with Ruff, format check, Pyright, and
  `18 passed`.
- `factory-runner` security scan:
  `uv run python -m security_scan.cli /Users/devon/Projects/factory-runner/.worktrees/ws41-factory-runner --category security`
  reported `BLOCK=0`, `WARN=0`, `INFO=1`
  (`bws.least-privilege-scope`, judgment-only).
- `orchestrator`: `SECURITY_STANDARDS_DIR=/Users/devon/Projects/security-standards make check`
  passed with `686 passed`.
- `orchestrator` security scan:
  `uv run python -m security_scan.cli /Users/devon/Projects/orchestrator/.worktrees/ws41-factory-runner --category security`
  reported `BLOCK=0`, `WARN=0`, `INFO=1`
  (`bws.least-privilege-scope`, judgment-only).
- `project-standards`: `uv run portfolio foundation` reported
  `violations=0 accepted=0 unknown=0`.
- Production health probes:
  - `https://sds.alobar.net/health/live` returned `200`.
  - `https://sds.alobar.net/health/ready` returned `200`.

## Commits

- `factory-runner`: `72288e9..51126e9`
- `orchestrator`: `c4aefe6..302100d`

## Scope Exclusions

- No orchestrator automatic dispatch.
- No automatic merge.
- No Phase 5 verifier logic.
- No tracker canonicalization.
- No brain learning or promotion.
- No graduation automation.
- No live production infrastructure mutation beyond read-only health checks.
