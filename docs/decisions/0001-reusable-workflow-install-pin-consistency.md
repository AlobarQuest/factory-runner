# 0001 — The reusable-workflow install pin must be functionally consistent with its own CLI invocations

- Status: Accepted (minimal fix applied 2026-07-29; functional-consistency guard deferred to the backlog)
- Date: 2026-07-29
- Deciders: Devon

## Context

`.github/workflows/factory-runner.yml` is a reusable workflow that consumer repos call. It does
**not** install the runner from `@main`. Instead it uses a **trusted bootstrap pin**: it installs a
specific reviewed factory-runner SHA and re-verifies that exact SHA at runtime
(`factory-runner verify-install-revision --expected "<sha>"`). This is a deliberate supply-chain
choice — a caller runs only a reviewed runner revision, not whatever `main` happens to be.

That pin is hardcoded in **three coupled places**:

1. the install step: `uv tool install "git+…/factory-runner.git@<sha>"`
2. the runtime verify step: `verify-install-revision --expected "<sha>"`
3. `tests/test_workflow_contract.py`, which asserts the workflow contains exactly that `<sha>`

The pin is advanced only by an explicit human commit (e.g. `fix: advance trusted runner bootstrap
pin`, 2026-07-14).

### The failure this ADR responds to

On 2026-07-24, commit `14907a3` ("emit cost actuals") added the `--execution-file` option to the
workflow's `finalize-run` / `fail-run` **invocations** and to the **CLI** — the two edits that must
move together — but left the install pin at `5ac7981`, a revision whose `finalize_run` / `fail_run`
predate `--execution-file`. The contract test stayed green because it only checks **SHA identity**
(pin == `5ac7981`), not **functional consistency** (does that SHA's CLI accept the options the
workflow passes?). Worse, factory-runner has no CI and `make check` is dead (see `PROJECT.md`), so
the test was not executed at all.

The break stayed latent until the first real dispatch since those features merged: GAP-4
(2026-07-29, a `httpx2` dependency update on `change-manager`). The runner installed CLI `5ac7981`,
ran the coding action successfully, then failed at `finalize-run` **and** `fail-run` with
`No such option: --execution-file` (exit 2), leaving the work unit stranded in `executing`. Full
incident record: orchestrator `docs/software-delivery-system/2026-07-29-gap4-first-dispatch-blocked-finalize-run-pin.md`.

This is the second of two hand-maintained pins in the dispatch chain that lagged silently; the
first was the caller → reusable-workflow ref (a consumer 15 commits stale), fixed separately.

## Decision

1. **Minimal fix (applied now):** advance the trusted pin from `5ac7981` to `c266769` in all three
   coupled sites. `c266769` is the current reviewed HEAD; it carries cost-actuals, the evidence-pack
   PR comment, and the lease-token fix, and — being the workflow's own revision — its CLI is
   consistent with the workflow's invocations by construction.
2. **Keep the trusted-bootstrap-pin model.** We deliberately do **not** switch the install to
   `@main`/HEAD. Installing a specific reviewed revision is the supply-chain property we want; the
   defect was the pin lagging, not the pinning itself.
3. **Defer the real guard (backlogged, not this session).** Replace the SHA-identity assertion with
   a **functional-consistency** check that installs the pinned CLI and verifies it accepts the exact
   options the workflow passes to each subcommand (`prepare-run`, `classify`, `finalize-run`,
   `fail-run`, `verify-install-revision`), and run it in CI. Until that lands, advancing the pin
   whenever the CLI surface changes remains a manual discipline.

## Consequences

- **Positive:** the immediate break is fixed and the supply-chain property is preserved. Any
  dispatch through the fixed workflow again reaches `finalize-run`.
- **Residual risk (accepted for now):** the pin is still hand-maintained across three sites with no
  functional guard, so the *same class* of bug can recur on the next change to the CLI surface until
  the deferred check and CI land. That work is tracked in `PROJECT.md`.
- **Consumer action required:** callers pinned to the *old* workflow SHA (e.g. `change-manager`
  pinned to `c266769`) do **not** receive this fix until they re-pin their caller to the merge SHA
  of the PR that applies this ADR. This is expected under the deliberate two-level pinning model.
