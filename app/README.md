# Fitness CLI Tools

Command-line tools for Fitbit and Strava APIs.

## Setup

### Prerequisites
- Python 3.14+
- Fitbit/Strava API credentials

### Install
```bash
# Using uv (recommended)
brew install uv
uv sync
```

### Environment
Create `.env` file with your API credentials:

```bash
# Fitbit - Required
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_REDIRECT_URI=https://localhost

# Strava - Required
STRAVA_CLIENT_ID=your_id
STRAVA_CLIENT_SECRET=your_secret
STRAVA_REDIRECT_URI=https://localhost
```

**Note:** Additional variables (ACCESS_TOKEN, REFRESH_TOKEN, EXPIRES_AT) are auto-generated during OAuth authentication and don't need to be declared manually.

## Usage

### Fitbit
```bash
# Authenticate
python -m app.fitbit fitbit-auth

# Get data
python -m app.fitbit fitbit-steps
python -m app.fitbit fitbit-sleep

# Token management
python -m app.fitbit fitbit-tokens
python -m app.fitbit fitbit-tokens-refresh
```

### Strava
```bash
# Authenticate
python -m app.strava strava-auth

# Get data
python -m app.strava strava-latest-workout

# Token management
python -m app.strava strava-tokens
python -m app.strava strava-tokens-refresh
```

## Docker

```bash
docker build -t fitness-cli .

# Interactive shell (recommended for auth/token operations)
docker run -it --env-file .env -v $(pwd):/app fitness-cli /bin/sh

# Direct command execution
docker run --env-file .env -v $(pwd):/app fitness-cli python -m app.fitbit fitbit-steps
```

**Note:** The `-v $(pwd):/app` volume mount is required when running commands that update files (like authentication), otherwise changes won't persist to your host machine.

## Files

- `oauth_manager.py` - OAuth handling
- `fitbit_client.py` - Fitbit API
- `strava_client.py` - Strava API
- `fitbit.py` - Fitbit CLI
- `strava.py` - Strava CLI

## GitHub Actions and recovery

The workflow runs every four hours and on pushes to main. PRs run offline validation.
It refreshes both services, fetches Strava once, and updates each profile line only when that service succeeds.
A failed service keeps previously retrieved data and makes the run fail after successful updates are published.
Strava failures show “Workouts unavailable” if no workout is saved.
A saved workout stays visible with a short notice that Strava updates are unavailable.
An unavailable Fitbit line can describe a previous day; it is not today's measurement.

Each service restores its newest unexpired token artifact independently. A failed data fetch does not discard successfully rotated tokens.
Runs are serialised because refresh tokens rotate. Do not cancel a run during rotation.
Token artifacts contain credentials; do not download or share them casually.

### Fitbit

An expired access token normally refreshes automatically. An `invalid_grant` refresh error requires new browser consent:

```bash
./scripts/refresh-fitbit-secrets.sh --dispatch
```

The helper requires `uv`, authenticated `gh`, and `.env` at the repository root.
It accepts an authorisation code silently, updates local tokens, sends secrets through stdin, and dispatches `main.yaml` with `skip_artifact=true`.
This bypasses previous artifacts for both services on the recovery run.

### Strava

Inspect the structured error before deciding to reauthorise:

- `Application / Status / Inactive`: inspect the application at https://www.strava.com/settings/api. Token refresh does not reactivate an application.
- Access or refresh authorisation failure: reauthorise and confirm the granted `activity:read` scope. Only Me activities require `activity:read_all`; request broader scope only if needed.
- Timeout or server failure: keep previous data and retry later.
- Successful empty activity list: the profile shows “No workouts yet.”

After restoring application access, if fresh authorisation is needed:

```bash
uv run python -m app.strava strava-auth
uv run python - <<'PYTHON'
import subprocess
from dotenv import dotenv_values
values = dotenv_values('.env')
for key in ('STRAVA_ACCESS_TOKEN', 'STRAVA_REFRESH_TOKEN'):
    value = values.get(key)
    if not value:
        raise SystemExit(f'Missing {key}')
    subprocess.run(['gh', 'secret', 'set', key], input=value, text=True, check=True)
expiry = values.get('STRAVA_EXPIRES_AT')
if not expiry:
    raise SystemExit('Missing STRAVA_EXPIRES_AT')
subprocess.run(['gh', 'variable', 'set', 'STRAVA_EXPIRES_AT', '--body', expiry], check=True)
PYTHON
gh workflow run main.yaml -f skip_artifact=true
```

Strava references: [authentication](https://developers.strava.com/docs/authentication/) and [activities](https://developers.strava.com/docs/reference/#api-Activities-getLoggedInAthleteActivities).

### Verify recovery

Use the run URL printed by the dispatch command:

```bash
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

Check data-fetch errors as well as token refresh. A successful refresh alone does not prove activity access.
Confirm the profile contains real data and that both token uploads succeeded. Never paste raw OAuth error bodies into logs or issues.

## Development

```bash
uv sync --frozen
uv run pytest
uv run pyright
uv run pre-commit run -a
```

CI also builds the production container and checks its imports without live API calls or development packages.
Tests use mocked services and temporary files; no credentials or browser consent are needed.
Python 3.14 is the minimum version and matches Docker, CI, Ruff, and type checks.
Pre-commit 4.6.2 and the other development tools are pinned by `uv.lock`; uv 0.12.21 is pinned in Docker and CI.

## Notes

- Access tokens refresh when expired; the workflow proactively refreshes to retain rotated tokens.
- `uv run python -m app.profile` updates the profile independently for each service and exits nonzero on any failure.
- API and OAuth requests have 30-second timeouts.
- `.env` and token JSON files are local credentials, excluded from Git and Docker build context.
