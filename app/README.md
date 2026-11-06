# Health Profile Updater

Google Health supplies steps and sleep; the signed-in Strava website supplies your newest workout.
The legacy Fitbit Web API and OAuth endpoints were retired on 2 November 2026. The old Fitbit CLI and recovery script cannot restore access.

## Google Health setup

1. In your Google Cloud project, enable Google Health API and configure an External OAuth client.
2. Add your Google Health account as a test user while setting up the integration.
3. Request only these scopes:
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
4. Create a Web application client with redirect URI `https://developers.google.com/oauthplayground` and download its JSON outside the checkout.
5. In OAuth Playground, use your own client credentials, Offline access and Consent Screen prompt. Authorise both scopes and exchange the code for tokens.
6. Run the helper from the repository root:

```bash
uv run python -m scripts.configure_google_health /path/to/downloaded-client.json
```

Paste the refresh token at the hidden prompt. The helper verifies your linked health account and today's steps/sleep before setting these repository secrets through stdin:

- `GOOGLE_HEALTH_CLIENT_ID`
- `GOOGLE_HEALTH_CLIENT_SECRET`
- `GOOGLE_HEALTH_REFRESH_TOKEN`

Requires authenticated `gh` with secret-write access to `o6uoq/o6uoq`. The helper does not save credentials locally, change OAuth publishing status or dispatch a workflow.

**Testing-mode refresh tokens expire after seven days.** Before unattended use, move the OAuth app to **In production**, then authorise again and rerun the helper with the final token. Personal-only apps can qualify for Google's verification exception; follow the console requirements for your project.

See [Google's migration guide](https://developers.google.com/health/migration), [setup](https://developers.google.com/health/setup) and [personal-use verification exception](https://support.google.com/cloud/answer/13464323).

## Runtime

The workflow runs every four hours, on pushes to main, and through manual dispatch. PRs run offline validation without credentials.
It refreshes the Google access token in memory using Google's OAuth library. Google refresh tokens are reusable, so the workflow no longer rotates Fitbit tokens or downloads/uploads token artifacts.

Steps use Google's reconciled `dailyRollUp` total (`steps.countSum`). Sleep uses reconciled sessions ending on that civil date and sums `summary.minutesAsleep`, including naps. Both use the same UTC date label as the old updater; the API interprets observations using their recorded local civil times. No sleep-stage algorithm is implemented locally.

Missing observations are unavailable, not measured zero. Before device sync or the first sleep session ending today, Google Health can return no observations; the updater retains the previous health line, marks it unavailable and fails the run. Explicitly observed zero steps are valid.

Strava is independent: a failure in either service preserves that service's previous data, allows the other service to update, then fails the workflow. A later successful fetch clears the unavailable notice. A green run alone does not establish accuracy; compare the published values with the provider.

For local Google Health reads, set the same three environment variables (or put them in a private root `.env`), then run:

```bash
uv run python -m app.google_health
```

API requests have 30-second timeouts. Errors never include raw OAuth/API bodies or credentials. A Google OAuth error needs Google reauthorisation; do not run the retired Fitbit recovery script.

## Strava

Set repository secrets `STRAVA_LOGIN` and `STRAVA_PASSWORD`. Your account must accept password login. No OAuth application is needed for workouts.

The Linux container runs Python 3.14.8, Camoufox 0.5.7 and the checksum-verified browser 156.0.1-beta.34. The uBlock Origin addon is pinned to 1.75.0 with its Mozilla checksum; the SDK verifies its fingerprint model. Runtime uses the browser, addon and model installed in the image.

Each run creates and removes a private browser profile, selects Strava's existing password form and uses the site's submission handler. It reads your own My Activities response, validates newest-first ordering and uses elapsed time rather than moving time. No desktop browser or saved session is required.

Strava's intermittent HTTP 403 is unresolved. Fixed request diagnostics report whether submitted email/password match the configured inputs and whether the CAPTCHA token is nonempty. They do not prove that Strava accepted the credentials or CAPTCHA.

The manual **Validate Health Profile App** workflow also checks a live Strava login on a GitHub runner. It does not write the profile. PR validation remains offline.

```bash
docker build -t fitness-cli .
docker run --rm --init --shm-size=256m --env-file .env fitness-cli uv run python -m app.strava strava-latest-workout
```

## Development and verification

Python 3.14 and `uv` are required. CI also builds the production container and checks imports with networking disabled and the checkout mounted at `/app`. Dependencies live in `/opt/venv` so the mount cannot hide them.

```bash
uv sync --frozen
uv run pytest
uv run pyright
uv run pre-commit run -a
```

After deployment, inspect actual provider outcomes and the committed README, not just token refresh or individual step colours:

```bash
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

Old Fitbit secrets/artifacts are not read by the new workflow. Do not delete stored credentials as part of the migration until real Google Health access and the production run have been verified.
