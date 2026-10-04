# Fitness CLI Tools

Command-line tools for the Fitbit API and your signed-in Strava activity list.

## Setup

### Prerequisites
- Python 3.14+
- Fitbit API credentials
- Strava email/password login and Linux Docker

### Install
```bash
# Using uv (recommended)
brew install uv
uv sync
```

### Environment
Create `.env` with your credentials:

```bash
# Fitbit - Required
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_REDIRECT_URI=https://localhost

# Strava website - Required for workouts
STRAVA_LOGIN=your_email
STRAVA_PASSWORD=your_password
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
# Fetch your newest workout in Linux Docker; output is name then elapsed duration.
docker run --rm --init --shm-size=256m --env-file .env fitness-cli uv run python -m app.strava strava-latest-workout
```

Your Strava account must accept password login. No OAuth application is needed for workouts.
Legacy `strava-auth`, `strava-tokens` and `strava-tokens-refresh` commands remain available for API use.

## Docker

```bash
docker build -t fitness-cli .

# Interactive shell (recommended for auth/token operations)
docker run -it --env-file .env -v $(pwd):/app fitness-cli /bin/sh

# Direct command execution
docker run --env-file .env -v $(pwd):/app fitness-cli uv run python -m app.fitbit fitbit-steps
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
It refreshes Fitbit tokens, fetches Strava once through its website, and updates each profile line only when that service succeeds.
A failed service keeps previously retrieved data and makes the run fail after successful updates are published.
Strava failures show “Workouts unavailable” if no workout is saved.
A saved workout stays visible with a short notice that Strava updates are unavailable.
An unavailable Fitbit line can describe a previous day; it is not today's measurement.

Fitbit restores its newest unexpired token artifact. A failed data fetch does not discard successfully rotated tokens.
Runs are serialised because refresh tokens rotate. Do not cancel a run during rotation.
Token artifacts contain credentials; do not download or share them casually.

### Fitbit

An expired access token normally refreshes automatically. An `invalid_grant` refresh error requires new browser consent:

```bash
./scripts/refresh-fitbit-secrets.sh --dispatch
```

The helper requires `uv`, authenticated `gh`, and `.env` at the repository root.
It accepts an authorisation code silently, updates local tokens, sends secrets through stdin, and dispatches `main.yaml` with `skip_artifact=true`.
This bypasses previous Fitbit artifacts on the recovery run.

### Strava

Set the repository secrets `STRAVA_LOGIN` and `STRAVA_PASSWORD` from your local `.env` through stdin:

```bash
uv run python - <<'PYTHON'
import subprocess
from dotenv import dotenv_values
values = dotenv_values('.env')
for key in ('STRAVA_LOGIN', 'STRAVA_PASSWORD'):
    value = values.get(key)
    if not value:
        raise SystemExit(f'Missing {key}')
    subprocess.run(['gh', 'secret', 'set', key], input=value, text=True, check=True)
PYTHON
```

The Ubuntu container runs Python 3.14.8, Camoufox 0.5.7 and the checksum-verified browser 156.0.1-beta.34.
The browser extension is pinned to uBlock Origin 1.75.0 with its Mozilla checksum; the SDK verifies its fingerprint model.
It runs a virtual display inside Linux, selects Strava's existing password form and uses the site's own submission handler.
Each run creates and removes its own browser profile. No desktop browser or saved session is required.
The workout comes from your own My Activities response and uses `elapsed_time_raw`, not moving time.
Website errors or changed response fields preserve the saved workout and fail the workflow.
This depends on Strava's current login-page implementation; a layout change can require an update.

The manual `Validate fitness CLI` workflow also checks a real Strava login on a GitHub runner.
Its Strava check only reads your activities; it does not refresh Fitbit or write the profile.
PR validation stays offline and does not receive login credentials.
Both workflows reuse GitHub build-layer caches for the installed browser and dependencies.
Caches contain build assets, not credentials or signed-in browser sessions.

### Verify recovery

Use the run URL printed by the dispatch command:

```bash
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

Check data-fetch errors as well as Fitbit token refresh. A successful refresh alone does not prove activity access.
Confirm the profile contains real data and the Fitbit token upload succeeded. Never paste raw OAuth error bodies into logs or issues.

## Development

```bash
uv sync --frozen
uv run pytest
uv run pyright
uv run pre-commit run -a
```

CI builds the production container and checks imports with the checkout mounted at `/app`, as in production.
Dependencies live in `/opt/venv` so the mount cannot hide them; the smoke test disables networking.
Tests use mocked services and temporary files; no credentials or browser consent are needed.
Python 3.14 is the minimum version and matches Docker, CI, Ruff, and type checks.
Pre-commit 4.6.2 and the other development tools are pinned by `uv.lock`; uv 0.12.22 is pinned in Docker and CI.

## Notes

- Access tokens refresh when expired; the workflow proactively refreshes to retain rotated tokens.
- `uv run python -m app.profile` updates the profile independently for each service and exits nonzero on any failure.
- API and OAuth requests have 30-second timeouts.
- `.env` and token JSON files are local credentials, excluded from Git and Docker build context.
