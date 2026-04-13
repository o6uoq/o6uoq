#!/usr/bin/env bash

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
DISPATCH="false"

if [[ "${1:-}" == "--dispatch" ]]; then
  DISPATCH="true"
fi

for cmd in uv gh grep cut; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

echo "Starting Fitbit OAuth re-authentication..."
uv run python -m app.fitbit fitbit-auth

get_env_value() {
  local key="$1"
  local value
  value=$(grep "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)

  if [[ -z "$value" ]]; then
    echo "Missing ${key} in ${ENV_FILE}" >&2
    exit 1
  fi

  printf '%s' "$value"
}

FITBIT_ACCESS_TOKEN=$(get_env_value "FITBIT_ACCESS_TOKEN")
FITBIT_REFRESH_TOKEN=$(get_env_value "FITBIT_REFRESH_TOKEN")
FITBIT_EXPIRES_AT=$(get_env_value "FITBIT_EXPIRES_AT")

echo "Updating GitHub Actions secrets/variables..."
gh secret set FITBIT_ACCESS_TOKEN --body "$FITBIT_ACCESS_TOKEN"
gh secret set FITBIT_REFRESH_TOKEN --body "$FITBIT_REFRESH_TOKEN"
gh variable set FITBIT_EXPIRES_AT --body "$FITBIT_EXPIRES_AT"

echo "Fitbit secrets and variable updated."

if [[ "$DISPATCH" == "true" ]]; then
  echo "Dispatching workflow with skip_artifact=true..."
  gh workflow run main.yaml -f skip_artifact=true
  echo "Workflow dispatched."
else
  echo "Next step: gh workflow run main.yaml -f skip_artifact=true"
fi
