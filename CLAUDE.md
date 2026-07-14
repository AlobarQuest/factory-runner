# Factory Runner Instructions

## Known Non-obvious Invariants

- Finalizer verification commands must use the target repository's local tool
  environment. When `.venv/bin` exists at the repository root, it precedes the
  inherited `PATH`; other runner subprocesses keep their inherited environment.
