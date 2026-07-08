#!/usr/bin/env bash
set -euo pipefail

: "${ORCHESTRATOR_URL:?ORCHESTRATOR_URL is required}"
: "${FACTORY_RUNNER_CREDENTIAL_KEY_ID:?FACTORY_RUNNER_CREDENTIAL_KEY_ID is required}"
: "${FACTORY_RUNNER_TOKEN:?FACTORY_RUNNER_TOKEN is required}"
: "${WORK_UNIT_ID:?WORK_UNIT_ID is required}"
: "${CURRENT_REPOSITORY:?CURRENT_REPOSITORY is required}"

factory-runner prepare \
  --orchestrator-url "$ORCHESTRATOR_URL" \
  --credential-key-id "$FACTORY_RUNNER_CREDENTIAL_KEY_ID" \
  --work-unit-id "$WORK_UNIT_ID" \
  --current-repository "$CURRENT_REPOSITORY"
