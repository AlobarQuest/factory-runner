# WS-P2.20 — factory-runner CI, Dependabot, and the workflow consistency guard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** factory-runner gets a gate that **refuses** rather than attests, runs in CI, receives
Dependabot updates, and proves its published workflow and its installed CLI agree.

**Architecture:** Every repo in the portfolio consumes factory-runner's reusable workflow, and
factory-runner has **no CI at all**. Worse, its `make check` is `command -v`-guarded on every tool,
so on a bare runner it exits 0 having verified nothing — adding CI without fixing that would produce
a green check that means nothing. Order therefore matters: find out what is actually broken, make the
gate refuse, then wire CI to it, then add the guard that closes the defect class that has already
cost a production run.

**Tech Stack:** Python 3.12, uv, ruff, pyright, pytest, GitHub Actions. Repo:
**`~/Projects/factory-runner`** (NOT orchestrator).

**Workstream:** WS-P2.20, Program Phase 2 Wave 4. Prerequisite for Wave 3's exit (the repo
onboarding), because onboarding five repos onto an untested runner builds on sand.

---

## Why this repo, and why now

factory-runner is the weakest structural point in the whole chain: **every onboarded repo `uses:` its
reusable workflow**, and nothing tests it. It has been an open P1 since before WS-P2.17.

The specific failure this closes is **GAP-4 attempt 1** (2026-07-29): the workflow installed the CLI
at one revision and invoked `finalize-run --execution-file`, an option only present in a later CLI.
Both `finalize-run` **and** `fail-run` exited 2 — so the runner could not even report its own failure,
and a recoverable failure became a stranded unit with a spent attempt. It was verified by hand,
18/18, in that session. Lint and type-checking would not have caught it.

---

## Global Constraints

- **The gate must REFUSE, not attest.** This is the standing P1 (*"enumerate every place the system
  ATTESTS rather than REFUSES"*). A `command -v` guard that prints "skipping" and exits 0 is the
  purest instance of it, and it is in the repo everything else depends on.
- **Read collected test counts, never check colours** — locally and in CI. `pytest` exit code 5
  ("no tests collected") must be a failure here, not a pass.
- **Do not change how pytest is invoked without checking import mode.** This repo's tests import
  siblings as `from test_cli import …`, not `from tests.test_cli import …`, because the Makefile runs
  bare `pytest` (rootdir-prepend mode). Changing the invocation to `python -m pytest`, adding
  `--import-mode=importlib`, or adding an `__init__.py` can break every test at collection. Verify
  with `.venv/bin/pytest` and read the collected count.
- **Do not touch `.github/workflows/factory-runner.yml`'s behaviour.** It is the reusable workflow
  every repo calls. You are adding a *test* of it, not editing it. If a genuine defect appears, stop
  and report — changing it is a cross-repo event.
- **factory-runner must stay public.** A reusable workflow called from repo X runs with X's
  `GITHUB_TOKEN`, so `uv tool install git+https://…` cannot authenticate against a private repo.
  Making it private breaks every caller.
- **This repo has no caller workflow and cannot be dispatched** — the work is hand-built, as
  WS-P2.16 U2 was.
- Merge per ruling R12: open the PR, read the CI collected count from the job log, verify your report
  obligations, merge yourself. **Do not deploy anything.**

---

## What HQ verified, so you need not re-derive it

- `.github/` contains **exactly one file**: `workflows/factory-runner.yml`. There is no quality
  workflow and no `dependabot.yml`.
- The `check` target today:

  ```make
  check:
  	@if command -v ruff >/dev/null 2>&1; then ruff check .; else echo "ruff not installed - skipping ruff check"; fi
  	@if command -v ruff >/dev/null 2>&1; then ruff format --check .; else echo "ruff not installed - skipping ruff format check"; fi
  	@if command -v pyright >/dev/null 2>&1; then pyright; else echo "pyright not installed - skipping pyright"; fi
  	@if command -v pytest >/dev/null 2>&1; then pytest; else echo "pytest not installed - skipping tests"; fi
  ```

- Dev tooling lives in **`[dependency-groups].dev`** — `pytest>=8.0`, `pyyaml>=6.0`, `ruff==0.15.20`,
  `pyright==1.1.411`. `uv sync` **does** install dependency-groups, so the portfolio-wide
  "`uv sync` installs no extras" trap does **not** apply here.
- `[tool.pytest.ini_options] testpaths = ["tests"]`; `[tool.pyright] typeCheckingMode = "basic"`,
  `venvPath = "."`, `venv = ".venv"`.
- There is **no `.code-standards.toml` and no `STANDARD_VERSION`** — the repo is not code-standards
  onboarded.
- `PROJECT.md` frontmatter is off-standard: `status: ws43-local-heavy-merged` (not a legal value),
  `purpose: 'TODO: one-line purpose'`, **no `required_checks`**, **no `applicable_standards`**,
  `updated: '2026-07-10'`, and both `project:` and `name:` keys.
- The workflow installs at `c266769fd9e9aecf4e35ced29ad1605656e84d87`, calls
  `verify-install-revision --expected <that sha>`, and invokes `prepare-run`, `finalize-run` and
  `fail-run` — the latter two with `--execution-file`.

---

### Task 1: Discovery — find out what is actually broken, before changing the gate

**No code changes in this task.** The point is to size the problem before committing to a fix, per
the standing rule that a verifier failing after your change usually failed before it too.

- [ ] **Step 1: Establish a working environment.**

```bash
cd ~/Projects/factory-runner
uv venv --clear && uv sync
```
(`uv venv` is not idempotent; `--clear` is.)

- [ ] **Step 2: Run each tool individually and record the real output.**

```bash
.venv/bin/ruff check . ; echo "ruff check rc=$?"
.venv/bin/ruff format --check . ; echo "ruff format rc=$?"
.venv/bin/pyright ; echo "pyright rc=$?"
.venv/bin/pytest ; echo "pytest rc=$?"
```

Record, for each: exit code, and the **count** (violations / errors / `collected N items`).

- [ ] **Step 3: STOP AND REPORT if the debt is large.**

If ruff or pyright report more than roughly **30** findings, or if any test fails, **stop here and
report the counts to HQ.** Burning down a large baseline is its own workstream, and code-standards
has a baseline mechanism designed for exactly that — adopting it is a different decision from fixing
a handful of violations, and it is HQ's call, not yours.

If the numbers are small, continue.

- [ ] **Step 4: Commit nothing.** Record the findings in your report.

---

### Task 2: The gate refuses

**Files:** `Makefile`

- [ ] **Step 1: Write the control first.**

Prove the current target lies. With the tools removed from `PATH`, `make check` must currently exit
**0**:

```bash
env PATH=/usr/bin:/bin make check ; echo "rc=$?"
```
Expected: `rc=0`, with "skipping" lines. **Paste this output into your report — it is the evidence
that the defect was real.**

- [ ] **Step 2: Rewrite `check` so every tool runs and every failure propagates.** Resolve tools from
      the repo-local `.venv/bin` (a global `pytest` can collect with the wrong interpreter), and make
      a missing tool a **hard error**, not a skip. **`pytest` exit code 5 (nothing collected) must
      fail**, not pass.

- [ ] **Step 3: Re-run the control.** With tools absent, `make check` must now exit **non-zero**.
      Paste it. Then run `make check` normally and confirm it passes with a real collected count.

- [ ] **Step 4: Fix whatever Task 1 surfaced**, if you got past its stop condition.

- [ ] **Step 5: Commit** — `fix(make): the check target refuses instead of attesting`

---

### Task 3: CI, and Dependabot

**Files:** `.github/workflows/quality.yml` (create), `.github/dependabot.yml` (create)

- [ ] **Step 1:** Read `~/Projects/orchestrator/.github/workflows/quality.yml` as the exemplar. This
      repo needs **no Postgres service and no `SECURITY_STANDARDS_DIR`** — it has neither dependency.
      Do not copy those in.
- [ ] **Step 2:** Write the workflow: checkout, uv, `uv sync`, `make check`. Trigger on push and
      pull_request. **The job log must show a collected count** — that is the artifact, not the
      green tick.
- [ ] **Step 3:** Write `.github/dependabot.yml` for the `uv`/pip ecosystem and for
      `github-actions`. The Actions ecosystem matters here specifically: this repo *is* a workflow.
- [ ] **Step 4: Commit** — `ci: add a quality workflow and Dependabot`

---

### Task 4: The manifest tells the truth

**Files:** `PROJECT.md`

- [ ] **Step 1:** Fix the frontmatter: a legal `status`, a real `purpose`, a current `updated`, and
      **`required_checks`** naming the workflow Task 3 added (executor grammar
      `github-actions:<file>[:<job>]`). Add `applicable_standards`. Decide `foundation:` deliberately
      — every onboarded repo consumes this repo's workflow — and **say what you chose and why** in
      the report.
- [ ] **Step 2:** Validate with the portfolio linter:

```bash
PYTHONPATH="$HOME/Projects/project-standards/src" python3 -m portfolio lint --repo ~/Projects/factory-runner
```
Report the before and after output.

- [ ] **Step 3: Commit** — `chore(manifest): bring PROJECT.md to the project standard`

---

### Task 5: The workflow and the CLI must agree

**Files:** `tests/test_workflow_contract.py` (extend — it exists and currently checks SHA identity
only)

This closes the GAP-4 class. SHA identity is not functional consistency: the workflow declared the
right revision and still invoked an option the installed CLI did not have.

- [ ] **Step 1: Write the failing test.**

Parse `.github/workflows/factory-runner.yml`, extract **every** `factory-runner <subcommand>
--option` invocation, and assert this repo's CLI accepts each one. Derive the accepted options from
the CLI itself — Typer/argparse introspection or `--help` — **not** from a hand-maintained list,
which would be a second vocabulary that can drift (this repo has already been bitten by exactly that
class).

- [ ] **Step 2: Prove it discriminates.** Temporarily add a `--nonexistent-option` to one invocation
      in a scratch copy of the workflow and confirm the test reds. Restore. **Record that you did
      this** — a guard built to detect a failure must be proven to FIRE.
- [ ] **Step 3:** Confirm it passes against the real workflow. If it **fails**, you have found a live
      defect of the GAP-4 class — **stop and report**; do not fix the workflow, because changing it
      is a cross-repo event affecting every caller.
- [ ] **Step 4: Commit** — `test(contract): the workflow's invocations must be accepted by the CLI`

---

### Task 6: The full gate

- [ ] **Step 1:** `git status` clean, then `make check`. Record the collected count.
- [ ] **Step 2:** Open the PR; confirm CI runs and **read the collected count from the job log**.
- [ ] **Step 3:** Merge per R12.

---

## Self-review notes

- **Deliberately out of scope:** code-standards onboarding (no `.code-standards.toml` /
  `STANDARD_VERSION`) — that is the conformance-kit work the repo onboarding will do, and doing it
  here would blur two decisions. Note its absence in your report.
- **Deliberately out of scope:** any behavioural change to `factory-runner.yml`. Task 5 tests it.
- **Known risk handed over:** Task 1 has unbounded discovery. Its stop condition exists so a large
  baseline becomes an HQ decision rather than an implementer's improvisation.
