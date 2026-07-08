# WS-4.3 Local-Heavy Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codify a manual local-heavy worker path that claims one approved orchestrator unit, executes under the existing authority envelope, opens evidence-bearing PRs, and submits evidence back to the production orchestrator without adding dispatch automation or merge authority.

**Architecture:** Extend the existing `factory-runner` Python package with local-heavy CLI commands that reuse the WS-4.1 authority validator, orchestrator client, evidence builders, and PR body renderer. Keep the orchestrator API as lifecycle truth and use only existing claim, renew, reclaim, command, runner-brief, and evidence endpoints.

**Tech Stack:** Python 3.12, Typer, Pydantic, httpx, pytest, ruff, pyright.

## Global Constraints

- Scope is WS-4.3 only: no WS-4.2 dispatch automation, WS-4.4 infra-lane linkage, Phase 5 verifier/release immutability, tracker canonicalization, brain learning/promotion, graduation automation, production deployment, or automatic merge.
- No worker may merge PRs.
- No raw token may be written to tracked files, prompts, logs, package YAML, evidence, PR bodies, or generated artifacts.
- Use the existing M2M credential shape: `X-Credential-Key-Id` plus `Authorization: Bearer <token>`.
- Stale or lost leases recover through orchestrator APIs, never private database edits.
- Repository and command scope come from the approved authority envelope.

---

### Task 1: Local-Heavy Client And CLI

**Files:**
- Modify: `src/factory_runner/client.py`
- Modify: `src/factory_runner/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces: `OrchestratorClient.renew(unit_id: str, *, attempt: int, lease_token: str, idempotency_key: str, expected_version: int | None = None) -> dict[str, Any]`
- Produces: `OrchestratorClient.reclaim_expired_claim(unit_id: str, *, next_owner_id: str, idempotency_key: str, expected_version: int | None = None, standing_context: dict[str, Any] | None = None) -> dict[str, Any]`
- Produces CLI commands: `local-heavy-prepare`, `local-heavy-renew`, `local-heavy-reclaim`, and `local-heavy-finalize`

- [ ] **Step 1: Write failing CLI tests**

Add tests proving `local-heavy-prepare` writes a sanitized local-heavy workspace, `local-heavy-renew` calls renew without printing the lease token, and `local-heavy-reclaim` uses the reclaim API path.

- [ ] **Step 2: Watch tests fail**

Run:

```bash
uv run pytest tests/test_cli.py::test_local_heavy_prepare_writes_sanitized_workspace tests/test_cli.py::test_local_heavy_renew_updates_workspace_without_printing_lease tests/test_cli.py::test_local_heavy_reclaim_uses_orchestrator_reclaim_api -v
```

Expected: fail because the commands do not exist.

- [ ] **Step 3: Write failing client tests**

Add tests proving `renew` posts to `/renew` and `reclaim_expired_claim` posts to `/reclaim-expired-claim`.

- [ ] **Step 4: Watch client tests fail**

Run:

```bash
uv run pytest tests/test_client.py::test_client_renews_claim tests/test_client.py::test_client_reclaims_expired_claim -v
```

Expected: fail because the methods do not exist.

- [ ] **Step 5: Implement the client and CLI**

Add the two client methods. Add local-heavy CLI commands by reusing the existing prepare/finalize logic with a local-heavy workspace default, local-heavy idempotency keys, explicit renew/reclaim commands, and no merge behavior.

- [ ] **Step 6: Verify focused tests pass**

Run:

```bash
uv run pytest tests/test_cli.py::test_local_heavy_prepare_writes_sanitized_workspace tests/test_cli.py::test_local_heavy_renew_updates_workspace_without_printing_lease tests/test_cli.py::test_local_heavy_reclaim_uses_orchestrator_reclaim_api tests/test_client.py::test_client_renews_claim tests/test_client.py::test_client_reclaims_expired_claim -v
```

Expected: all selected tests pass.

### Task 2: Local-Heavy Evidence And Docs

**Files:**
- Modify: `src/factory_runner/cli.py`
- Create: `docs/local-heavy-runtime.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_package_import.py`

**Interfaces:**
- Produces: local-heavy run manifests with `"runtime": "local-heavy"`
- Produces: operator documentation with decision criteria, claim/renew/reclaim/finalize commands, BWS-only secret loading, no private DB edits, and no merge behavior.

- [ ] **Step 1: Write failing tests**

Add tests proving local-heavy finalize submits runner evidence without leaking the lease token, and docs contain the required safety phrases.

- [ ] **Step 2: Watch tests fail**

Run:

```bash
uv run pytest tests/test_cli.py::test_local_heavy_finalize_submits_evidence_without_leaking_lease tests/test_package_import.py::test_local_heavy_docs_cover_safety_contract -v
```

Expected: fail because docs and finalize behavior are not complete.

- [ ] **Step 3: Implement docs and finalize marker**

Add docs. Ensure local-heavy manifests carry `"runtime": "local-heavy"` and finalize keeps lease tokens out of stdout, PR bodies, and evidence payload summaries beyond the API-required command field.

- [ ] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest tests/test_cli.py::test_local_heavy_finalize_submits_evidence_without_leaking_lease tests/test_package_import.py::test_local_heavy_docs_cover_safety_contract -v
```

Expected: all selected tests pass.

### Task 3: Full Verification

**Files:**
- No new implementation files.

**Interfaces:**
- Produces: verified WS-4.3 branch state.

- [ ] **Step 1: Run package gate**

Run:

```bash
make check
```

Expected: ruff, format check, pyright, and pytest pass.

- [ ] **Step 2: Run security scan**

Run:

```bash
PYTHONPATH="$HOME/Projects/security-standards/src" python3 -m security_scan.cli . --category security
```

Expected: `0 BLOCK`, `0 WARN`; any INFO is judgment-only and reported.

- [ ] **Step 3: Run portfolio foundation**

Run:

```bash
cd ~/Projects/project-standards && uv run portfolio foundation
```

Expected: `violations=0 accepted=0 unknown=0`.

- [ ] **Step 4: Smoke production endpoint assumptions**

Run health and M2M checks without printing secret values.

Expected: live 200, ready 200, missing M2M 401, configured M2M 200.
