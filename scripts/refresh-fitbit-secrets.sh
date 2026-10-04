#!/usr/bin/env bash

set -euo pipefail

ENV_FILE=".env"
cd "$(dirname "$0")/.."
DISPATCH="false"
usage() {
  echo "Usage: ./scripts/refresh-fitbit-secrets.sh [--dispatch]"
  echo "Reauthorise Fitbit and sync GitHub credentials; --dispatch starts recovery."
}

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi
case "${1:-}" in
  "") ;;
  --dispatch) DISPATCH="true" ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

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

chmod 600 "$ENV_FILE"
echo "Reauthorise Fitbit: approve activity/sleep, then enter the redirect code."
uv run --frozen python -m app.fitbit fitbit-auth

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

echo "Syncing Fitbit credentials to GitHub..."
printf '%s' "$FITBIT_ACCESS_TOKEN" | gh secret set FITBIT_ACCESS_TOKEN
printf '%s' "$FITBIT_REFRESH_TOKEN" | gh secret set FITBIT_REFRESH_TOKEN
gh variable set FITBIT_EXPIRES_AT --body "$FITBIT_EXPIRES_AT"

echo "Fitbit credentials synced."

if [[ "$DISPATCH" == "true" ]]; then
  gh workflow run main.yaml --ref main -f skip_artifact=true
else
  echo "Start recovery: gh workflow run main.yaml --ref main -f skip_artifact=true"
fi
